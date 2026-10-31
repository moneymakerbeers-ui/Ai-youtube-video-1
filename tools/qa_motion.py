#!/usr/bin/env python3
"""qa_motion.py - motion QA INSIDE every transition of a rendered file, plus short motion previews for the eyes.

usage:
  python tools/qa_motion.py FILE --plan render/plan-long.json [--trace render/trace-long.json] [--thresholds library/thresholds.json]
         [--narration audio/narration.wav] [--out qa/motion-long.json] [--previews render/previews/long]
  python tools/qa_motion.py --selfcheck        (only run the instruments on synthetic transitions with known defects and print how each was classified)
exit: 0 PASSED · 1 FAILED · 3 BLOCKED (a measurement could not run or the detectors failed their self-check) · 2 usage

What is measured, per transition window of the DELIVERED file (decoded frames, not the renderer's intentions):
  boundary   the window starts and ends without a pop: the change at its first/last frame is not a spike against the window's own motion
  exposure   luma/colour never leaves the range between the two ends (flash risk) and no single frame step is large
  stall      the picture does not freeze inside the middle of the window: frames the renderer drew moving that the file shows duplicated, or an operator
             whose own progress stands still mid-move (the settled tail of an ease is not a stall; without the renderer's trace the file alone is judged)
  pop        no interior frame jumps away from its neighbours and settles again (a one-frame zoom, a wrong frame, a stray cut)
  anchor     (renderer trace) the anchors land where the plan says at both ends, stay locked together, stay on the straight line between their two
             rest positions, travel monotonically, and are not stretched (uniform-scale types keep their aspect)
  smooth     (heuristic) no inter-frame motion spike
  ghost      (heuristic) a semi-transparent double image where the type promises a match, not a crossfade
  audio      (heuristic) no abrupt level step or click at the window edges
Mechanical checks (boundary, exposure, stall, pop, anchor) FAIL; heuristics (smooth, ghost, audio) only WARN. Heuristics are never proof of quality and a pass here does not replace looking at the previews:
render/previews/<target>/tr-<from>-<to>.mp4 (the window +-0.5 s with its audio) and tr-<from>-<to>-strip.png (10 frames across it).
Before judging the file the instruments are run on synthetic transitions with KNOWN defects (a good eased dissolve, a hard pop, a white
flash frame, a frozen middle) and must classify all four correctly; if not, every check is BLOCKED.
QA_FAULT=bad_filter|selfcheck_fail|drop_frames|anchor_break injects faults for the tests.
"""
import argparse, json, math, os, shutil, sys, tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import decode_mono, read_json  # noqa: E402
from qa_core import Report, run_tool  # noqa: E402

DEFAULTS = {
    "padS": 0.3,
    "width": 192,
    "boundary": {"spikeFactor": 4.0, "minLevels": 8.0},
    "exposure": {"bulgeLevels": 20.0, "pulseLevels": 8.0, "pulseWindow": 13, "maxStepLevels": 14.0},
    "stall": {"frames": 4, "innerFraction": 0.7, "maxDiffLevels": 6.0, "stuckProgress": [0.05, 0.95]},
    "smooth": {"factor": 1.8, "minLevels": 2.0},
    "pop": {"factor": 2.5, "minLevels": 3.0, "floorLevels": 1.0},
    "anchor": {"endpointTolFrac": 0.015, "lockTolFrac": 0.006, "pathTolFrac": 0.008, "monotoneTolFrac": 0.01, "aspectTol": 0.03},
    "ghost": {"warnAbove": 0.6},
    "audio": {"stepDb": 12.0, "clickRatio": 8.0, "floorDb": -60.0},
    "previews": {"padS": 0.5, "strip": 10},
}
UNIFORM_SCALE = ("match_geometry", "focus_bridge", "nested_scale")
LOCKED = ("match_geometry", "focus_bridge", "truthful_morph")
ANCHORED = ("match_geometry", "match_movement", "nested_scale", "occlusion_reveal", "depth_through_object", "focus_bridge", "truthful_morph")


def merge(a, b):
    for k, v in b.items():
        a[k] = merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


# ───────────────────────────── decoding ─────────────────────────────
def decode_frames(path, t0, n, width, fault=()):
    """n frames from t0 as float32 [n, H, W, 3] at `width` px wide (area-averaged). Returns (frames, problem or None)."""
    pr = run_tool(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    if pr.rc != 0 or "," not in pr.out:
        return None, f"ffprobe could not read the frame size: {pr.tail()}"
    sw, sh = map(int, pr.out.strip().split(",")[:2])
    H = 2 * round(sh * width / sw / 2)
    vf = f"scale={width}:{H}:flags=area"
    if "bad_filter" in fault:
        vf += ",nosuchfilter=x=1"
    r = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(t0, 0):.4f}", "-i", path, "-frames:v", str(n), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], binary=True)
    if r.rc != 0 or r.fatal_lines():
        return None, f"ffmpeg decode failed (exit {r.rc}): {(r.fatal_lines() or [r.tail()])[0]}"
    buf = np.frombuffer(r.out, dtype=np.uint8)
    per = width * H * 3
    got = len(buf) // per
    if "drop_frames" in fault:
        got = max(got - 6, 0)
    if got <= 0:
        return None, "ffmpeg returned no frames for the window"
    return buf[: got * per].reshape(got, H, width, 3).astype(np.float32), None


def luma(fr):
    return fr[..., 0] * 0.299 + fr[..., 1] * 0.587 + fr[..., 2] * 0.114


def pooled(g):  # 2 x 2 block mean: the same 96-px-wide pooled picture the stillness gate uses (codec noise averages out, small movers stay visible)
    n, h, w = g.shape
    return g[:, : h // 2 * 2, : w // 2 * 2].reshape(n, h // 2, 2, w // 2, 2).mean(axis=(2, 4))


def edges(g):
    gx = np.abs(np.diff(g, axis=1))[:-1, :]
    gy = np.abs(np.diff(g, axis=0))[:, :-1]
    return gx + gy


# ───────────────────────────── per-window measurements (pure; used on the file and on the synthetic self-check media) ─────────────────────────────
def measure_window(frames, i0, i1, th):
    """frames: [n,H,W,3]; the transition occupies frames i0..i1 inclusive (indices into frames). Returns the metric record."""
    g = luma(frames)
    L = g.mean(axis=(1, 2))
    C = frames.mean(axis=(1, 2))
    P = pooled(g)
    D = np.zeros(len(g))
    Dmax = np.zeros(len(g))
    for k in range(1, len(g)):
        D[k] = np.abs(g[k] - g[k - 1]).mean()
        Dmax[k] = np.abs(P[k] - P[k - 1]).max()
    return {"L": L, "C": C, "D": D, "Dmax": Dmax, "g": g, "i0": i0, "i1": i1}


def check_boundary(m, th):
    i0, i1, D = m["i0"], m["i1"], m["D"]
    win = D[i0 + 1: i1 + 1] if i1 > i0 else D[i0: i0 + 1]
    med = float(np.median(win)) if len(win) else 0.0
    ref = max(med, 1.0)
    worst, where = 0.0, None
    for k in (i0, i0 + 1, i1, i1 + 1):
        if 0 < k < len(D) and D[k] > worst:
            worst, where = float(D[k]), k
    bad = worst > th["boundary"]["minLevels"] and worst > th["boundary"]["spikeFactor"] * ref
    return (not bad), worst, med, where


def check_exposure(m, th):
    """Flash risk and exposure jumps, measured the way flashing is defined (fast opposing changes), not as 'brightness differs from the ends':
      step    no single frame-to-frame change of mean luma above maxStepLevels (a hard cut or a flash frame)
      pulse   no short excursion: luma against its own rolling median over pulseWindow frames (a 1-3 frame flash, even when each step is modest)
      bulge   no large slow excursion: luma never leaves the range between the two ends by more than bulgeLevels (a slow dip through white/black)
    A smooth, small swell mid-transition (a zoom that enlarges a bright outline) is none of these. Returns (ok, worst excursion, worst step, worst colour excursion)."""
    E = th["exposure"]
    i0, i1, L, C = m["i0"], m["i1"], m["L"], m["C"]
    a = float(np.mean(L[max(i0 - 2, 0): i0 + 1])) if i0 >= 0 else float(L[0])
    b = float(np.mean(L[i1: min(i1 + 3, len(L))]))
    inside = L[i0: i1 + 1]
    bulge = float(max(inside.max() - max(a, b), min(a, b) - inside.min(), 0.0))
    step = float(np.abs(np.diff(L[max(i0 - 1, 0): i1 + 2])).max()) if len(L) > 1 else 0.0
    w = E["pulseWindow"] // 2
    pulse = 0.0
    for k in range(i0, min(i1, len(L) - 1) + 1):
        lo, hi = max(k - w, 0), min(k + w + 1, len(L))
        pulse = max(pulse, abs(float(L[k]) - float(np.median(L[lo:hi]))))
    ca, cb = C[max(i0, 0)], C[min(i1, len(C) - 1)]
    cin = C[i0: i1 + 1]
    cover = float(max((cin - np.maximum(ca, cb)).max(), (np.minimum(ca, cb) - cin).max(), 0.0))
    ok = bulge <= E["bulgeLevels"] and pulse <= E["pulseLevels"] and cover <= E["bulgeLevels"] * 1.5 and step <= E["maxStepLevels"]
    return ok, max(bulge, pulse), step, cover


def frozen_frame(k, Dm, T, ctx, th):
    """Is delivered frame k a frozen/duplicated one? The file alone cannot tell a frozen frame from a SETTLED one (the long tail of an ease, where the
    renderer's own pictures barely differ). With the renderer's trace it can: frozen means the renderer drew motion the file does not show (frames
    were duplicated or dropped after rendering), or the operator's own progress stood still in the middle of its move (an engine fault)."""
    if not (k < len(Dm) and Dm[k] <= T):
        return False
    if not ctx or not ctx.get("src"):
        return True  # no usable source series: judge on the file alone (fail-closed: settled tails can then look frozen)
    fr = ctx["frame0"] + k
    sd = ctx["src"].get(fr)
    if sd is not None and sd > 2 * T:
        return True
    e0, e1 = ctx["e"].get(fr - 1), ctx["e"].get(fr)
    lo, hi = th["stall"]["stuckProgress"]
    return e0 is not None and e1 is not None and abs(e1 - e0) < 1e-6 and lo < e1 < hi


def check_stall(m, th, ctx=None):
    i0, i1, Dm = m["i0"], m["i1"], m["Dmax"]
    n = i1 - i0 + 1
    f = th["stall"]["innerFraction"]
    a, b = i0 + int(round(n * (1 - f) / 2)), i1 - int(round(n * (1 - f) / 2))
    T = th["stall"]["maxDiffLevels"]
    run, best, at = 0, 0, None
    for k in range(a, b + 1):
        if frozen_frame(k, Dm, T, ctx, th):
            run += 1
            if run > best:
                best, at = run, k - run + 1
        else:
            run = 0
    return best < th["stall"]["frames"], best, at


def local_spike(D, lo_k, hi_k, factor, min_levels):
    """The largest frame step in [lo_k, hi_k) that stands out from the median of its own six neighbours: (k, rise above them, their median) or None.
    Eased motion changes smoothly from frame to frame, so a legitimately FAST peak (a zoom, a push) passes while a jump that settles again does not."""
    worst, where, ref_w = 0.0, None, 0.0
    for k in range(max(lo_k, 1), min(hi_k, len(D))):
        nb = np.concatenate([D[max(k - 3, 1):k], D[k + 1:min(k + 4, len(D))]])
        if len(nb) < 3:
            continue
        ref = float(np.median(nb))
        rise = float(D[k]) - ref
        if rise >= min_levels and D[k] >= factor * max(ref, 1.0) and rise > worst:
            worst, where, ref_w = rise, k, ref
    return (where, worst, ref_w) if where is not None else None


def check_smooth(m, th):
    """(heuristic) a smaller jerk than a pop: a frame step 1.8x its neighbours and 2+ levels above them. Returns (ok, rise, neighbour median)."""
    P = th["smooth"]
    r = local_spike(m["D"], m["i0"] + 1, m["i1"] + 1, P["factor"], P["minLevels"])
    return (r is None), (r[1] if r else 0.0), (r[2] if r else 0.0)


def check_pop(m, th):
    """An interior frame that jumps away from its neighbours and settles again (a one-frame zoom, a wrong frame, a stray cut). The window edges belong
    to the boundary check, so only interior steps are judged. Returns (ok, rise_levels, neighbour_median, frame)."""
    P = th["pop"]
    r = local_spike(m["D"], m["i0"] + 2, m["i1"], P["factor"], P["minLevels"])
    return (r is None), (r[1] if r else 0.0), (r[2] if r else 0.0), (r[0] if r else None)


def corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def ghost_score(m):
    i0, i1, g = m["i0"], m["i1"], m["g"]
    mid = (i0 + i1) // 2
    ea, eb, em = edges(g[max(i0 - 1, 0)]), edges(g[min(i1 + 1, len(g) - 1)]), edges(g[mid])
    return min(corr(em, ea), corr(em, eb))


# ───────────────────────────── trace-based anchor checks ─────────────────────────────
def check_anchor(frames_tr, typ, W, H, th):
    """frames_tr: the trace's per-frame transition records for one window. Returns (ok, messages)."""
    A = th["anchor"]
    msgs = []
    fs = [f for f in frames_tr if f.get("aOut")]
    if len(fs) < 3:
        return True, []  # nothing to measure (operator without an anchor path)
    first, last = fs[0], fs[-1]
    tol = A["endpointTolFrac"] * max(W, H)
    if first["a"] and math.hypot(first["aOut"]["cx"] - first["a"]["cx"], first["aOut"]["cy"] - first["a"]["cy"]) > tol * 4:  # small step into the window
        msgs.append("the anchor of the outgoing scene moves at the very first frame")
    if typ in LOCKED:
        lk = [f for f in fs if f.get("bOut")]
        worst = max((math.hypot(f["aOut"]["cx"] - f["bOut"]["cx"], f["aOut"]["cy"] - f["bOut"]["cy"]) for f in lk), default=0.0)
        if worst > A["lockTolFrac"] * max(W, H):
            msgs.append(f"the two anchors drift {worst:.1f}px apart (they must stay locked)")
        if last.get("b") and last.get("bOut") and math.hypot(last["bOut"]["cx"] - last["b"]["cx"], last["bOut"]["cy"] - last["b"]["cy"]) > tol:
            msgs.append("the incoming anchor does not land on its own rest position at the end of the window")
        # monotone travel along the start->end line and monotone (geometric) scale
        c0, c1 = (fs[0]["aOut"]["cx"], fs[0]["aOut"]["cy"]), (last["bOut"]["cx"], last["bOut"]["cy"]) if last.get("bOut") else (last["aOut"]["cx"], last["aOut"]["cy"])
        dx, dy = c1[0] - c0[0], c1[1] - c0[1]
        dd = dx * dx + dy * dy
        # the anchor stays on the straight line between its two rest positions (a sideways jerk or a one-frame jump leaves it, even when both anchors jump together)
        dev = 0.0
        for f in fs:
            px, py = f["aOut"]["cx"] - c0[0], f["aOut"]["cy"] - c0[1]
            if dd > 1.0:
                u = max(0.0, min(1.0, (px * dx + py * dy) / dd))
                px, py = px - u * dx, py - u * dy
            dev = max(dev, math.hypot(px, py))
        if dev > A["pathTolFrac"] * max(W, H):
            msgs.append(f"the anchor leaves the straight line between its two rest positions by {dev:.1f}px")
        if dd > 1.0:
            s = [((f["aOut"]["cx"] - c0[0]) * dx + (f["aOut"]["cy"] - c0[1]) * dy) / dd for f in fs]
            back = max((s[i] - s[i + 1] for i in range(len(s) - 1)), default=0.0)
            if back > A["monotoneTolFrac"]:
                msgs.append(f"the anchor travels backwards along its path (by {back * 100:.1f}% of the move)")
        w = [f["aOut"]["w"] for f in fs]
        ww = max((abs(math.log(w[i + 1] / w[i])) for i in range(len(w) - 1) if w[i] > 0 and w[i + 1] > 0), default=0.0)
        total = abs(math.log(max(w[-1], 1e-6) / max(w[0], 1e-6))) if w[0] > 0 else 0.0
        if total > 0.05 and ww > 0.6 * total:
            msgs.append("the anchor's scale jumps: one frame carries most of the change")
    if typ in UNIFORM_SCALE:
        asp = [f["aOut"]["w"] / f["aOut"]["h"] for f in fs if f["aOut"]["h"] > 0]
        if asp and (max(asp) / min(asp) - 1) > A["aspectTol"]:
            msgs.append(f"the anchor's aspect ratio changes by {(max(asp) / min(asp) - 1) * 100:.1f}% (a uniform-scale transition must not stretch)")
    return not msgs, msgs


# ───────────────────────────── audio ─────────────────────────────
def audio_edges(x, sr, t_edges, words, th, ref=None):
    """x mono float32 (the delivered audio). Returns a list of (t, kind, value) for abrupt steps/clicks at the given edge times.
    A step is not reported when the voice itself makes it: near a word onset/offset, or when the narration alone (`ref`, the stem the mix was built
    from) steps by a comparable amount at the same moment. What stays is what the mix or the transition added."""
    A = th["audio"]
    hop = int(sr * 0.01)
    n = len(x) // hop
    if n < 4:
        return []
    e = 10 * np.log10(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    er = None
    if ref is not None and len(ref) // hop >= 4:
        m = min(len(ref) // hop, n)
        er = 10 * np.log10(np.mean(ref[: m * hop].reshape(m, hop) ** 2, axis=1) + 1e-12)
    onsets = [w["s"] for w in words] + [w["e"] for w in words]

    def voice_step(k):
        if er is None:
            return False
        lo, hi = max(k - 3, 1), min(k + 4, len(er))
        return any(abs(er[j] - er[j - 1]) > 0.5 * abs(e[k] - e[k - 1]) for j in range(lo, hi))

    out = []
    for t in t_edges:
        c = int(t * 100)
        for k in range(max(c - 15, 1), min(c + 15, n)):
            if e[k] > A["floorDb"] and e[k - 1] > A["floorDb"] and abs(e[k] - e[k - 1]) > A["stepDb"] and not any(abs(k / 100 - o) < 0.08 for o in onsets) and not voice_step(k):
                out.append((k / 100, "step", float(abs(e[k] - e[k - 1]))))
        seg = x[max(int((t - 0.1) * sr), 1): int((t + 0.1) * sr)]
        if len(seg) > 10:
            d = np.abs(np.diff(seg))
            rms = float(np.sqrt(np.mean(seg ** 2))) + 1e-6
            if float(d.max()) / rms > A["clickRatio"] and rms > 10 ** (A["floorDb"] / 20):
                out.append((t, "click", float(d.max() / rms)))
    return out


# ───────────────────────────── instrument self-check on known transitions ─────────────────────────────
def synth_transition(kind, d):
    """A 3 s 384x216 clip, transition window 1.0-2.0 s between two scenes with a rectangle each: good | pop | flash | stall."""
    A = "color=c=0x1c2540:s=384x216:r=30:d=3,drawbox=x=40:y=40:w=140:h=90:color=0xffb454:t=fill[a]"
    B = "color=c=0x3a5a4a:s=384x216:r=30:d=3,drawbox=x=200:y=90:w=140:h=90:color=0x5ad1c4:t=fill[b]"
    # eased cross-dissolve over 1.0-2.0 s (smoothstep of time)
    ease = "(3*pow(clip((T-1)/1,0,1),2)-2*pow(clip((T-1)/1,0,1),3))"
    if kind == "good":
        mix = f"[a][b]blend=all_expr='A*(1-{ease})+B*{ease}'"
    elif kind == "pop":  # hard cut at 1.5 s inside the 1 s window
        mix = "[a][b]blend=all_expr='if(lt(T,1.5),A,B)'"
    elif kind == "flash":  # same dissolve plus a 2-frame white flash at 1.5 s
        mix = f"[a][b]blend=all_expr='if(between(T,1.5,1.5666),255,A*(1-{ease})+B*{ease})'"
    elif kind == "stall":  # the dissolve holds still from 1.25 to 1.75 s, then catches up continuously (time warp: freeze, then 3x speed)
        te = "if(lt(T,1.25),T,if(lt(T,1.75),1.25,if(lt(T,2),1.25+(T-1.75)*3,T)))"
        e2 = f"(3*pow(clip(({te}-1)/1,0,1),2)-2*pow(clip(({te}-1)/1,0,1),3))"
        mix = f"[a][b]blend=all_expr='A*(1-{e2})+B*{e2}'"
    else:
        raise ValueError(kind)
    out = os.path.join(d, f"{kind}.mkv")
    r = run_tool(["ffmpeg", "-v", "error", "-y", "-filter_complex", f"{A};{B};{mix},format=yuv420p[v]", "-map", "[v]", "-c:v", "ffv1", out])
    return out if r.rc == 0 else None, r


def selfcheck(th, table=None):
    problems = []
    d = tempfile.mkdtemp(prefix="qam-self-")
    try:
        expect = {"good": {"pass": ("boundary", "exposure", "stall", "smooth", "pop"), "fail": ()},
                  "pop": {"pass": (), "fail": ("smooth", "exposure", "pop")},  # a hard cut is a spike in motion AND a brightness step
                  "flash": {"pass": (), "fail": ("exposure", "pop")},
                  "stall": {"pass": ("boundary", "exposure"), "fail": ("stall",)}}
        for kind, want in expect.items():
            f, r = synth_transition(kind, d)
            if not f:
                problems.append(f"could not synthesise the {kind} transition: {r.tail()}")
                continue
            fr, bad = decode_frames(f, 0.0, 90, th["width"])
            if bad or fr is None or len(fr) < 85:
                problems.append(f"could not decode the {kind} transition: {bad}")
                continue
            m = measure_window(fr, 30, 60, th)
            res = {"boundary": check_boundary(m, th)[0], "exposure": check_exposure(m, th)[0], "stall": check_stall(m, th)[0], "smooth": check_smooth(m, th)[0], "pop": check_pop(m, th)[0]}
            if table is not None:
                table.append((kind, res, want))
            for c in want["pass"]:
                if not res[c]:
                    problems.append(f"the {c} check failed a {kind} transition that is fine for it")
            for c in want["fail"]:
                if res[c]:
                    problems.append(f"the {c} check missed the defect in the {kind} transition")
    except FileNotFoundError as e:
        problems.append(f"tool missing: {e}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return (not problems), problems


# ───────────────────────────── previews ─────────────────────────────
def previews(path, tr, th, outdir, fps, dur):
    os.makedirs(outdir, exist_ok=True)
    pad = th["previews"]["padS"]
    t0, t1 = max(tr["startS"] - pad, 0.0), min(tr["endS"] + pad, dur)
    name = f"tr-{tr['from']}-{tr['to']}"
    mp4, strip = os.path.join(outdir, name + ".mp4"), os.path.join(outdir, name + "-strip.png")
    r1 = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", path, "-vf", "scale=480:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", mp4])
    n = th["previews"]["strip"]
    r2 = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", path, "-vf", f"fps={n / max(t1 - t0, 0.1):.4f},scale=320:-2,tile={min(n, 5)}x{math.ceil(n / 5)}:padding=4:margin=4:color=black", "-frames:v", "1", strip])
    return (mp4 if r1.rc == 0 and os.path.exists(mp4) else None), (strip if r2.rc == 0 and os.path.exists(strip) else None), (r1.tail() if r1.rc else r2.tail())


# ───────────────────────────── main ─────────────────────────────
def run_selfcheck(th, fault):
    table = []
    try:
        ok, problems = selfcheck(th, table)
    except Exception as e:  # noqa: BLE001
        ok, problems = False, [f"the self-check could not run: {e}"]
    if "selfcheck_fail" in fault:
        ok, problems = False, ["injected: self-check failure"]
    for kind, res, want in table:
        print(f"  {kind:<6} " + "  ".join(f"{c}={'ok' if v else 'FLAGGED'}" for c, v in res.items()) + f"   (must pass: {', '.join(want['pass']) or '-'}; must flag: {', '.join(want['fail']) or '-'})")
    if ok:
        print("SELFCHECK PASSED: the instruments classified a good eased dissolve, a hard pop, a white flash and a frozen middle correctly")
        return 0
    print("BLOCKED: the motion instruments failed on transitions with known defects: " + "; ".join(problems))
    return 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--plan")
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--narration", help="the narration stem the mix was built from (steps the voice itself makes are not reported as abrupt audio)")
    ap.add_argument("--trace")
    ap.add_argument("--thresholds")
    ap.add_argument("--out")
    ap.add_argument("--previews")
    ap.add_argument("--no-previews", action="store_true")
    a = ap.parse_args()
    th = json.loads(json.dumps(DEFAULTS))
    if a.thresholds and os.path.exists(a.thresholds):
        t = read_json(a.thresholds)
        merge(th, t.get("qaMotion", {}))
    fault = set(filter(None, os.environ.get("QA_FAULT", "").split(",")))
    if a.selfcheck:
        return run_selfcheck(th, fault)
    if not a.file or not a.plan:
        ap.error("FILE and --plan are required (or use --selfcheck)")
    if not os.path.exists(a.file):
        print(f"no such file: {a.file}", file=sys.stderr)
        return 2
    plan = read_json(a.plan)
    trace = read_json(a.trace) if a.trace and os.path.exists(a.trace) else None
    rep = Report(a.file, "motion")
    W, H, fps, dur = plan["width"], plan["height"], plan["fps"], plan["durationS"]
    trs = [dict(s["transitionOut"], **{"from": s["id"], "to": plan["scenes"][i + 1]["id"]}) for i, s in enumerate(plan["scenes"][:-1]) if s.get("transitionOut")]
    for tool in ("ffmpeg", "ffprobe"):
        try:
            if run_tool([tool, "-version"]).rc != 0:
                raise FileNotFoundError(tool)
        except FileNotFoundError:
            rep.blocked("tools", f"{tool} is not available; nothing was measured")
            return finish(a, rep, [])
    if not trs:
        rep.add("motion", "info", 0, "the plan has no transitions (only cuts); nothing to measure")
        return finish(a, rep, [])
    ok, problems = selfcheck(th)
    if "selfcheck_fail" in fault:
        ok, problems = False, ["injected: self-check failure"]
    rep.add("selfcheck", "pass" if ok else "blocked", None, "the motion instruments classified a good eased dissolve, a hard pop, a white flash and a frozen middle correctly" if ok else "the motion instruments failed on transitions with known defects: " + "; ".join(problems))
    x = None
    has_audio = run_tool(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", a.file]).out.strip()
    if has_audio:
        try:
            x = decode_mono(a.file, 16000)
        except Exception as e:  # noqa: BLE001
            rep.add("audio.decode", "blocked", None, f"the audio could not be decoded for the edge checks: {str(e)[-200:]}")
    else:
        rep.add("audio.decode", "info", None, "the file has no audio stream; audio edge checks skipped")
    words = plan.get("words", [])
    ctx_all = None
    if trace and (trace.get("sourceMotion") or {}).get("ymax") and not trace["sourceMotion"].get("error") and trace["sourceMotion"].get("pool") == th["width"] // 2:
        sm = trace["sourceMotion"]
        r0 = trace["range"][0]
        ctx_all = {"src": {sm["first"] - r0 + j: v for j, v in enumerate(sm["ymax"])}, "e": {f["f"]: f["e"] for f in trace.get("transitionFrames", [])}}
    nar_ref = None
    if a.narration and os.path.exists(a.narration):
        try:
            nar_ref = decode_mono(a.narration, 16000)
        except Exception:  # noqa: BLE001
            nar_ref = None  # the stem could not be decoded: every step is judged on the delivered audio alone (more warnings, never fewer)
    out_tr = []
    for tr in trs:
        tid = f"{tr['from']}>{tr['to']}"
        typ = tr["type"]
        info = {"id": tid, "type": typ, "startS": tr["startS"], "endS": tr["endS"]}
        pad = th["padS"]
        s0 = max(tr["startS"] - pad, 0.0)
        n = int(round((min(tr["endS"] + pad, dur) - s0) * fps)) + 1
        frames, bad = decode_frames(a.file, s0, n, th["width"], fault)
        if frames is None or len(frames) < n - 2:
            cause = bad or f"decoded {0 if frames is None else len(frames)} of {n} frames for the window"
            for c in ("boundary", "exposure", "stall", "pop"):
                rep.add(f"motion.{tid}.{c}", "blocked", None, cause)
            out_tr.append(info)
            continue
        i0 = int(round((tr["startS"] - s0) * fps))
        i1 = min(int(round((tr["endS"] - s0) * fps)), len(frames) - 2)
        m = measure_window(frames, i0, i1, th)
        if not ok:
            for c in ("boundary", "exposure", "stall", "pop"):
                rep.add(f"motion.{tid}.{c}", "blocked", None, "the motion instruments failed their self-check")
        else:
            okb, worst, med, where = check_boundary(m, th)
            rep.add(f"motion.{tid}.boundary", "pass" if okb else "fail", round(worst, 1), f"{typ}: the change at the window edges ({worst:.1f} levels at frame +{(where or 0) - i0}) is in line with the window's own motion (median {med:.1f})" if okb else f"{typ} pops at the window edge: a {worst:.1f}-level frame change at {s0 + (where or 0) / fps:.2f}s against a median of {med:.1f}")
            oke, over, step, cover = check_exposure(m, th)
            rep.add(f"motion.{tid}.exposure", "pass" if oke else "fail", {"excursion": round(over, 1), "step": round(step, 1)}, f"{typ}: no flash or exposure jump (largest frame step {step:.1f} levels, largest excursion {over:.1f})" if oke else f"{typ} flashes: luma excursion {over:.1f} levels, colour excursion {cover:.1f}, largest frame step {step:.1f} levels (flash risk)")
            oks, run, at = check_stall(m, th, dict(ctx_all, frame0=int(round(s0 * fps))) if ctx_all else None)
            rep.add(f"motion.{tid}.stall", "pass" if oks else "fail", run, f"{typ}: the picture keeps moving through the middle of the window" if oks else f"{typ} stalls: {run} identical frames from {s0 + (at or 0) / fps:.2f}s inside the window (frozen or duplicated frames)")
            okp, rise, nb, wp = check_pop(m, th)
            rep.add(f"motion.{tid}.pop", "pass" if okp else "fail", round(rise, 1), f"{typ}: no interior frame jumps away from its neighbours (steadiest {rise:.1f} levels above them)" if okp else f"{typ} pops: the frame step at {s0 + (wp or 0) / fps:.2f}s is {rise:.1f} levels above its neighbours' typical {nb:.1f} and settles again (a one-frame jump)")
            okm, mx, ref = check_smooth(m, th)
            rep.add(f"motion.{tid}.smooth", "pass" if okm else "warn", round(mx, 1), "inter-frame motion changes smoothly (no frame step stands out from its neighbours)" if okm else f"a frame step is {mx:.1f} levels above its neighbours' typical {ref:.1f} (a jerk; smaller than a pop)", heuristic=True)
            if typ not in ("dissolve", "truthful_morph"):
                gs = ghost_score(m)
                rep.add(f"motion.{tid}.ghost", "pass" if gs <= th["ghost"]["warnAbove"] else "warn", round(gs, 2), "no strong double image mid-window" if gs <= th["ghost"]["warnAbove"] else f"mid-window edges resemble BOTH ends ({gs:.2f}): this looks like a crossfade, not a {typ}", heuristic=True)
        # anchors from the renderer's own per-frame geometry
        if typ in ANCHORED:
            if not trace or not trace.get("transitionFrames"):
                rep.add(f"motion.{tid}.anchor", "blocked", None, "no render trace with per-frame anchor geometry was supplied (--trace); anchor continuity is unverified")
            else:
                fs = [f for f in trace["transitionFrames"] if f["from"] == tr["from"] and f["to"] == tr["to"]]
                if not fs:
                    rep.add(f"motion.{tid}.anchor", "blocked", None, "the trace has no frames for this transition")
                else:
                    oka, msgs = check_anchor(fs, typ, W, H, th)
                    if "anchor_break" in fault:
                        oka, msgs = False, msgs + ["injected (QA_FAULT=anchor_break): the anchors drifted apart"]
                    used = {f["used"] for f in fs}
                    if used != {typ}:
                        msgs = msgs + [f"the renderer used {sorted(used)} instead of the planned {typ} (fell back)"]
                        oka = False
                    rep.add(f"motion.{tid}.anchor", "pass" if oka else "fail", len(fs), f"{typ}: anchors land, stay locked and travel monotonically over {len(fs)} frames" if oka else f"{typ}: " + "; ".join(msgs))
        # audio at the window edges
        if x is not None:
            ev = audio_edges(x, 16000, [tr["startS"], tr["endS"]], words, th, nar_ref)
            rep.add(f"motion.{tid}.audio", "pass" if not ev else "warn", len(ev), "no abrupt level step or click at the window edges" if not ev else "abrupt audio at " + "; ".join(f"{t:.2f}s {k} {v:.1f}" for t, k, v in ev[:4]), heuristic=True)
        if not a.no_previews:
            pdir = a.previews or os.path.join(os.path.dirname(os.path.abspath(a.out or a.file)), "previews")
            mp4, strip, err = previews(a.file, tr, th, pdir, fps, dur)
            info.update({"preview": mp4, "strip": strip})
            rep.add(f"motion.{tid}.preview", "info" if mp4 and strip else "warn", None, f"view {strip} (10 frames) and play {mp4}; the numbers above are heuristics, the eyes decide" if mp4 and strip else f"the motion preview could not be written: {err}")
        out_tr.append(info)
    return finish(a, rep, out_tr)


def finish(a, rep, transitions):
    rep.print()
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(rep.to_json(file=a.file, transitions=transitions), open(a.out, "w"), indent=2)
    return rep.exit_code


if __name__ == "__main__":
    sys.exit(main())
