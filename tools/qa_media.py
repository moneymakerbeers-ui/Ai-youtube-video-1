#!/usr/bin/env python3
"""qa_media.py - machine gates for ONE rendered video file. Fail-closed: a gate passes only with evidence.

usage:
  python tools/qa_media.py FILE --plan render/plan-long.json [--allow qa/allow-long.json] [--tokens style-tokens.json]
         [--master audio/master-long.wav] [--thresholds library/thresholds.json] [--out qa/long.json] [--sheets qa/sheets/long]
exit: 0 PASSED · 1 FAILED (something unplanned or wrong was measured) · 3 BLOCKED (a measurement could not run or be trusted) · 2 usage

What "fail-closed" means here (v2 read ffmpeg's output without looking at its exit code, so a broken filter graph produced
empty logs and every gate passed):
  - every subprocess exit code is checked, and the log is scanned for [error]/[fatal]/"No such filter"/"Invalid argument";
  - every metadata stream is checked for coverage (frames sampled vs frames expected; last timestamp vs duration);
  - before the file is judged, the detectors are run on 3 s of synthetic media with KNOWN black/static/silent spans and must
    find exactly those; if they do not, the detector gates are BLOCKED, not green;
  - black, stillness and silence are tolerated only inside windows the plan names (make_allow.py), must lie INSIDE them, and a
    declared black must actually be there. There is no blanket allowance;
  - stillness is measured twice: exactly at the renderer (scene-graph hashes, zero tolerance, authorised by the plan's holds and
    rests) and in the delivered file (largest change of any block of the pooled picture between consecutive frames, which sees
    small movers that freezedetect's whole-frame mean misses). The file may be still only where the scene graph is still (give or
    take the sub-detection tail of an eased move), so frozen or duplicated frames are caught.
Tests inject faults with the QA_FAULT environment variable (bad_filter, bad_audio_filter, drop_metadata, selfcheck_fail).
Heuristic checks (flash, unexplained cuts) are labelled and never counted as proof.
"""
import argparse, json, math, os, re, shutil, sys, tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import decode_mono, read_json  # noqa: E402
from make_allow import build_allow  # noqa: E402
from qa_core import Report, contained, diffs_by_frame, fmt_iv, motion_chain, parse_black, parse_loudness, parse_series, parse_silence, run_tool, selfcheck, still_runs  # noqa: E402

DEFAULTS = {
    "expect": {"long": {"w": 1920, "h": 1080}, "short": {"w": 1080, "h": 1920, "maxS": 180}},
    "loudness": {"targetLufs": -14.0, "toleranceLu": 1.5, "maxTruePeakDbtp": -1.0},
    "freeze": {"minS": 0.4, "pool": 96, "maxDiffLevels": 6, "capLevels": 14, "slopS": 0.3, "visibleFactor": 2},
    "black": {"minS": 0.03, "pixTh": 0.10},
    "silence": {"minS": 0.7, "noiseDb": -45},
    "narration": {"silentBelowDbOfMedian": 35.0, "minWords": 3, "minS": 0.5},
    "cuts": {"score": 0.35, "tolS": 0.12},
    "flash": {"lumaDelta": 20, "swingsPerSecond": 6},
    "avSyncMaxS": 0.10,
    "sync": {"maxLagS": 0.05},
    "coverage": {"minFraction": 0.985},
}


def frac(x, default=0.0):
    try:
        n, d = str(x).split("/")
        return float(n) / float(d) if float(d) else default
    except Exception:  # noqa: BLE001
        return default


def merge(a, b):
    for k, v in b.items():
        a[k] = merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--plan")
    ap.add_argument("--allow")
    ap.add_argument("--tokens")
    ap.add_argument("--kind", choices=["long", "short"])
    ap.add_argument("--master")
    ap.add_argument("--trace", help="render/trace-<target>.json from engine/render.ts (state hashes: stillness measured at the source)")
    ap.add_argument("--thresholds")
    ap.add_argument("--out")
    ap.add_argument("--sheets")
    ap.add_argument("--every", type=float)
    a = ap.parse_args()
    th = json.loads(json.dumps(DEFAULTS))
    if a.thresholds and os.path.exists(a.thresholds):
        merge(th, read_json(a.thresholds).get("qa", read_json(a.thresholds)))
    fault = set(filter(None, os.environ.get("QA_FAULT", "").split(",")))
    if not os.path.exists(a.file):
        print(f"no such file: {a.file}", file=sys.stderr)
        return 2
    plan = read_json(a.plan) if a.plan else None
    tokens = read_json(a.tokens) if a.tokens and os.path.exists(a.tokens) else None
    allow = read_json(a.allow) if a.allow else (build_allow(plan, tokens) if plan else None)
    rep = Report(a.file)

    # ── tools ──
    for tool in ("ffmpeg", "ffprobe"):
        try:
            r = run_tool([tool, "-version"])
            if r.rc != 0:
                raise FileNotFoundError(tool)
        except FileNotFoundError:
            rep.blocked("tools", f"{tool} is not available; install ffmpeg and re-run (nothing was measured)")
            return finish(a, rep, None, [])
    # ── is the instrument itself trustworthy? ──
    ok, problems = selfcheck(th)
    if "selfcheck_fail" in fault:
        ok, problems = False, ["injected: self-check failure"]
    if not ok:
        rep.add("selfcheck", "blocked", None, "the detectors failed on synthetic media with known events: " + "; ".join(problems))
    else:
        rep.add("selfcheck", "pass", None, "blackdetect, the stillness instrument (incl. a 1 px/frame crawling square), silencedetect, signalstats and ebur128 found exactly the known events in synthetic media")

    # ── probe ──
    pr = run_tool(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", a.file])
    info = None
    try:
        info = json.loads(pr.out) if pr.rc == 0 else None
    except Exception:
        info = None
    if not info or not info.get("format") or not float(info["format"].get("duration", 0) or 0) > 0:
        rep.blocked("probe", "ffprobe could not read a duration/streams from the file", pr)
        return finish(a, rep, None, [])
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    kind = a.kind or ((plan or {}).get("layout") == "portrait" and "short") or ("short" if vs and vs["height"] > vs["width"] else "long")
    dur = float(info["format"]["duration"])
    fps = float(plan["fps"]) if plan else ((frac(vs["avg_frame_rate"]) if vs else 0.0) or 30.0)
    probe_checks(rep, info, vs, au, kind, plan, th, dur)
    if vs is None:
        return finish(a, rep, info, [])

    # ── decode every frame at full resolution, count them ──
    dec = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-stats", "-i", a.file, "-map", "0:v:0", "-f", "null", "-"])
    frames = re.findall(r"frame=\s*(\d+)", dec.err)
    decode_errs = [l.strip() for l in dec.err.splitlines() if l.strip() and not l.strip().startswith(("frame=", "size=", "video:"))]
    if dec.rc != 0:
        rep.blocked("decode", f"full decode exited with {dec.rc}", dec)
    elif decode_errs:
        rep.add("decode", "fail", len(decode_errs), "decode reported errors: " + " | ".join(decode_errs[:3]))
    elif not frames:
        rep.blocked("decode", "the decode pass reported no frame count", dec)
    else:
        n = int(frames[-1])
        want = plan["durationFrames"] if plan else None
        if want is not None and abs(n - want) > 1:
            rep.add("decode", "fail", n, f"decoded {n} frames, the plan has {want}")
        else:
            rep.add("decode", "pass", n, f"{n} frames decoded without a diagnostic" + (f" (plan: {want})" if want else ""))

    afps = fps if fps <= 30.5 else fps / 2  # analysis rate: every frame up to 30 fps, every other frame above
    video_gates(rep, a, vs, dur, afps, allow, th, fault, ok, plan)
    if au:
        audio_gates(rep, a, au, dur, allow, th, fault, ok, plan)
    sheets = make_sheets(rep, a, kind, allow, dur) if a.sheets else []
    return finish(a, rep, info, sheets)


def finish(a, rep, info, sheets):
    rep.print()
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(rep.to_json(file=a.file, sheets=sheets, probe=({"duration": info["format"].get("duration")} if info else None)), open(a.out, "w"), indent=2)
    return rep.exit_code


# ───────────────────────────── probe ─────────────────────────────
def probe_checks(rep, info, vs, au, kind, plan, th, dur):
    if not vs:
        rep.add("probe.video", "fail", None, "no video stream")
        return
    exp = {"w": plan["width"], "h": plan["height"]} if plan else th["expect"][kind]
    okdim = (vs["width"], vs["height"]) == (exp["w"], exp["h"])
    rep.add("probe.size", "pass" if okdim else "fail", f'{vs["width"]}x{vs["height"]}', f'expected {exp["w"]}x{exp["h"]}' + (" (from the plan)" if plan else f" for {kind}"))
    rep.add("probe.codec", "pass" if vs["codec_name"] == "h264" and vs.get("pix_fmt") == "yuv420p" else "fail", f'{vs["codec_name"]}/{vs.get("pix_fmt")}', "expected h264 + yuv420p")
    rep.add("probe.color", "pass" if vs.get("color_space") == "bt709" and vs.get("color_range") == "tv" else "fail", f'{vs.get("color_space", "untagged")}/{vs.get("color_range", "untagged")}', "expected bt709 / tv tags")
    cfr = vs.get("r_frame_rate") == vs.get("avg_frame_rate")
    rep.add("probe.fps", "pass" if cfr and (not plan or abs(frac(vs["r_frame_rate"]) - plan["fps"]) < 0.01) else "fail", f'{vs.get("r_frame_rate")} vs {vs.get("avg_frame_rate")}', f"constant frame rate expected" + (f" = {plan['fps']}" if plan else ""))
    if plan:
        want = plan["durationS"]
        rep.add("probe.duration", "pass" if abs(dur - want) <= 1.5 / plan["fps"] + 0.03 else "fail", round(dur, 3), f"plan duration {want}s")
    if kind == "short":
        mx = th["expect"]["short"]["maxS"]
        rep.add("short.length", "pass" if dur <= mx else "fail", round(dur, 2), f"a Short must be <= {mx}s")
    if not au:
        rep.add("probe.audio", "fail", None, "no audio stream")
        return
    rep.add("probe.audio", "pass" if au["codec_name"] == "aac" and int(au.get("sample_rate", 0)) in (44100, 48000) else "fail", f'{au["codec_name"]} {au.get("sample_rate")}Hz {au.get("channels")}ch', "expected aac at 44.1/48 kHz")
    if vs.get("duration") and au.get("duration"):
        d = abs(float(vs["duration"]) - float(au["duration"]))
        rep.add("av.duration", "pass" if d <= th["avSyncMaxS"] else "fail", round(d, 3), f'audio and video lengths differ by {d:.3f}s (max {th["avSyncMaxS"]})')


# ───────────────────────────── video gates ─────────────────────────────
def crop_expr(region):
    if not region:
        return ""
    return f"crop=iw*{region['w']}:ih*{region['h']}:iw*{region['x']}:ih*{region['y']},"


def video_gates(rep, a, vs, dur, afps, allow, th, fault, selfcheck_ok, plan):
    vdur = float(vs.get("duration") or dur)
    expect_n = int(round(vdur * afps))
    tmp = tempfile.mkdtemp(prefix="qa-v-")
    luma, score = os.path.join(tmp, "luma.txt"), os.path.join(tmp, "score.txt")
    fpsf = f"fps={afps}," if abs(afps - frac(vs["avg_frame_rate"], afps)) > 0.01 else ""

    # pass 1: full frame — black, luma series (flash), scene scores (heuristic cuts)
    chain = f'{fpsf}scale=320:-2,blackdetect=d={th["black"]["minS"]}:pix_th={th["black"]["pixTh"]},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={luma},select=gte(scene\\,0),metadata=print:key=lavfi.scene_score:file={score}'
    if "bad_filter" in fault:
        chain += ",nosuchfilter=x=1"
    p1 = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+info", "-i", a.file, "-map", "0:v:0", "-vf", chain, "-an", "-f", "null", "-"])
    if "drop_metadata" in fault and os.path.exists(luma):
        open(luma, "w").write("")
    ys = parse_series(luma, "lavfi.signalstats.YAVG")
    sc = parse_series(score, "lavfi.scene_score")
    p1_ok = True
    if p1.rc != 0 or p1.fatal_lines():
        p1_ok = False
        cause = f"the video analysis pass failed (exit {p1.rc}): {(p1.fatal_lines() or [p1.tail()])[0]}"
        for gate in ("black", "flash", "cuts"):
            rep.blocked(gate, cause, p1)
    else:
        need = th["coverage"]["minFraction"] * expect_n
        last = ys[-1][0] if ys else 0.0
        if len(ys) < need or last < vdur - 3.0 / afps - 0.1:
            p1_ok = False
            cause = f"luma metadata covers {len(ys)} of {expect_n} frames (last sample at {last:.2f}s of {vdur:.2f}s); the file was not fully analysed"
            for gate in ("black", "flash", "cuts"):
                rep.blocked(gate, cause, p1)
    if p1_ok:
        if not selfcheck_ok:
            rep.blocked("black", "the detectors did not pass their self-check")
        else:
            black = parse_black(p1.err)
            windows = [(w["fromS"], w["toS"]) for w in (allow or {}).get("black", [])]
            tol = (allow or {}).get("tolS", 1.5 / afps + 0.03)
            bad = [ev for ev in black if not contained(ev, windows, tol)]
            missing = [w for w in (allow or {}).get("black", []) if w.get("mustExist") and not any(min(e[1], w["toS"]) - max(e[0], w["fromS"]) > 0 for e in black)]
            if bad:
                rep.add("black", "fail", len(bad), f"unplanned black at {fmt_iv(bad)}; the plan authorises black only in {fmt_iv(windows) or 'no window'}")
            elif missing:
                rep.add("black", "fail", len(missing), "declared black is not there: " + "; ".join(f"{m['reason']} ({m['fromS']}-{m['toS']}s)" for m in missing))
            else:
                rep.add("black", "pass", len(black), f"{len(black)} black span(s), all inside declared windows" if black else "no black frames, none declared")
        # flash heuristic
        swings = [ys[i + 1][0] for i in range(len(ys) - 1) if abs(ys[i + 1][1] - ys[i][1]) >= th["flash"]["lumaDelta"]]
        worst, at, j = 0, 0.0, 0
        for i, t in enumerate(swings):
            while swings[j] < t - 1.0:
                j += 1
            if i - j + 1 > worst:
                worst, at = i - j + 1, t
        rep.add("flash", "pass" if worst < th["flash"]["swingsPerSecond"] else "fail", worst, "heuristic for the 3-flashes rule (large mean-luma swings in 1 s), not a conformance test" if worst < th["flash"]["swingsPerSecond"] else f"{worst} large brightness swings within 1 s near {at:.2f}s", heuristic=True)
        # unexplained jumps (heuristic)
        planned = (allow or {}).get("plannedCutsS", [])
        wins = [(t["startS"], t["endS"]) for t in (allow or {}).get("transitions", [])]
        jumps = [t for t, v in sc if v > th["cuts"]["score"] and t > 0.1 and not any(abs(t - p) <= th["cuts"]["tolS"] for p in planned) and not any(s - 0.1 <= t <= e + 0.1 for s, e in wins)]
        rep.add("cuts", "pass" if not jumps else "warn", len(jumps), f"jumps the plan does not explain at {[round(t, 2) for t in jumps[:8]]}" if jumps else "every large frame change is a planned cut or inside a planned transition", heuristic=True)

    # pass 2: stillness. (a) at the renderer, exactly; (b) in the delivered file, on the picture without captions
    region = (allow or {}).get("pictureRegion") if allow else None
    trace = read_json(a.trace) if a.trace and os.path.exists(a.trace) else None
    src_runs = trace_still_runs(trace) if trace else None
    ally = allow or {}
    if trace:
        ev = [r for r in (src_runs or []) if r[1] - r[0] >= th["freeze"]["minS"]] if src_runs is not None else None
        if src_runs is None:
            rep.add("freeze.source", "blocked", None, "the render trace has no state hashes")
        else:
            eval_freeze(rep, "freeze.source", ev, ally, "the scene graph at the renderer (before encoding)", 0.0)
    central = allow is not None and "pictureRegion" in allow and allow["pictureRegion"] is None
    if central:
        rep.add("freeze", "info" if trace else "blocked", None, "captions sit in the centre of the frame, so stillness in the delivered file cannot be separated from caption motion" + ("; the scene graph was checked at the source (freeze.source)" if trace else "; supply --trace (state hashes from the renderer) to check it at the source"))
    else:
        video_stillness(rep, a, th, fault, selfcheck_ok, vs, vdur, afps, fpsf, region, ally, src_runs, tmp, source_series(trace, th, region))
    shutil.rmtree(tmp, ignore_errors=True)


def video_stillness(rep, a, th, fault, selfcheck_ok, vs, vdur, afps, fpsf, region, allow, src_runs, tmp, src_series=None):
    F = th["freeze"]
    sink = os.path.join(tmp, "motion.txt")
    chain = motion_chain(crop_expr(region), fpsf, F["pool"], sink)
    if "bad_filter" in fault:
        chain += ",nosuchfilter=x=1"
    p2 = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+info", "-i", a.file, "-map", "0:v:0", "-vf", chain, "-an", "-f", "null", "-"])
    if "drop_metadata" in fault and os.path.exists(sink):
        open(sink, "w").write("")
    if p2.rc != 0 or p2.fatal_lines():
        rep.blocked("freeze", f"the stillness pass failed (exit {p2.rc}): {(p2.fatal_lines() or [p2.tail()])[0]}", p2)
        return
    series = parse_series(sink, "lavfi.signalstats.YMAX")
    expect = int(round(vdur * afps)) - 1
    last = series[-1][0] if series else 0.0
    if len(series) < th["coverage"]["minFraction"] * expect or last < vdur - 4.0 / afps - 0.1:
        rep.blocked("freeze", f"the stillness metadata covers {len(series)} of {expect} frame pairs (last sample at {last:.2f}s of {vdur:.2f}s); the file was not fully analysed", p2)
        return
    if not selfcheck_ok:
        rep.blocked("freeze", "the detectors did not pass their self-check")
        return
    diffs = diffs_by_frame(series, afps)
    T = F["maxDiffLevels"]
    # calibrate on the file itself: frames the scene graph says are identical show only codec noise
    noise = None
    if src_runs is not None:
        edge = int(round(F["slopS"] * afps))
        quiet = []
        fades = [(b["fromS"] - F["slopS"], b["toS"] + F["slopS"]) for b in (allow or {}).get("black", [])]  # a declared fade is applied after the scene graph: its frames are not "identical" in the file

        def in_fade(k):
            return any(a0 <= k / afps <= a1 for a0, a1 in fades)
        for sa, sb in src_runs:
            quiet += [diffs[k] for k in range(int(round(sa * afps)) + edge + 1, int(round(sb * afps)) - edge) if k in diffs and not in_fade(k)]
        if len(quiet) >= 30:
            q = sorted(quiet)
            noise = q[min(len(q) - 1, int(0.99 * len(q)))]
            T = max(T, int(math.ceil(noise)) + 2)
            if T > F["capLevels"]:
                rep.add("freeze", "blocked", {"noiseFloor": noise}, f"codec noise in frames the scene graph says are identical reaches {noise:.0f} levels; the stillness instrument cannot tell noise from motion above {F['capLevels']} (re-encode with a lower CRF or raise freeze.capLevels knowingly)")
                return
    runs = still_runs(diffs, afps, T, F["minS"])
    note = f"threshold {T} levels on a {F['pool']}-px pooled picture" + (f" (codec noise in still frames: {noise:.0f})" if noise is not None else "")
    what = "the delivered picture (captions excluded)"
    if src_runs is not None:
        slop = F["slopS"]
        # What the delivered file is compared with. With the renderer's own probe (same chain, before encoding) the reference is "the
        # source changes by no more than visibleFactor x the threshold" - a slow ease tail that changes by 1-3 levels is not a frame that
        # was lost. Without the probe the reference falls back to identical scene-graph states, which cannot see sub-visible change.
        ref, ref_what = src_runs, "a span where the scene graph is still"
        if src_series is not None:
            if src_series.get("error"):
                rep.add("freeze", "blocked", None, "the renderer's motion probe is unusable: " + src_series["error"])
                return
            sd = src_series["diffs"]
            ref = still_runs(sd, afps, T * F["visibleFactor"], 0.0, n_frames=src_series["n"])
            ref_what = f"a span where the source changes by at most {T * F['visibleFactor']} levels on the same pooled picture"
        bad = [(x, y) for x, y in runs if not any(x >= sa - slop and y <= sb + slop for sa, sb in ref)]
        if bad:
            rep.add("freeze", "fail", len(bad), f"frozen frames: {what} is still at " + "; ".join(f"{x:.2f}-{y:.2f}s" for x, y in bad[:5]) + f" while the source is visibly changing there (dropped or duplicated frames, or motion outside the picture crop such as an entity inside the caption zone); {note}")
        else:
            rep.add("freeze", "pass", len(runs), f"{len(runs)} still span(s) in {what}, each inside {ref_what} (±{slop}s); {note}" if runs else f"{what} never holds still for {F['minS']}s or more; {note}")
        # the reverse: noise where the scene graph is identical (visible shimmer in a hold)
        edge = int(round(F["slopS"] * afps))
        shimmer = []
        for sa, sb in src_runs:
            ks = [k for k in range(int(round(sa * afps)) + edge + 1, int(round(sb * afps)) - edge) if k in diffs]
            run = []
            for k in ks + [None]:
                if k is not None and diffs[k] > T:
                    run.append(k)
                else:
                    if len(run) >= 3:
                        shimmer.append((run[0] / afps, run[-1] / afps))
                    run = []
        if shimmer:
            rep.add("freeze.shimmer", "warn", len(shimmer), "the file changes by more than the noise threshold where the scene graph is still: " + "; ".join(f"{x:.2f}-{y:.2f}s" for x, y in shimmer[:4]) + " (encoder pumping or a caption in the picture crop)", heuristic=True)
    else:
        eval_freeze(rep, "freeze", runs, allow, what, F["slopS"], extra=note, perceptual=True)


def source_series(trace, th, region=None):
    """The renderer's own pooled-difference series (render.ts runs the same chain before encoding) as {absolute frame: level}, or None for a
    trace that predates the probe, or {"error": ...} when the probe is present but unusable (that blocks, it is not ignored)."""
    sm = (trace or {}).get("sourceMotion")
    if not sm:
        return None
    if sm.get("error"):
        return {"error": sm["error"]}
    if sm.get("pool") != th["freeze"]["pool"]:
        return {"error": f"the probe pooled the picture to {sm.get('pool')} px but the QA uses {th['freeze']['pool']} px; render again or set freeze.pool"}
    a, b = sm.get("region"), region
    same = (a is None and b is None) or (a is not None and b is not None and all(abs(a[k] - b[k]) < 1e-6 for k in ("x", "y", "w", "h")))
    if not same:
        return {"error": f"the renderer measured the picture region {a} but the QA crops {b}; the plan changed after this render, render again"}
    first, y = sm["first"] - trace["range"][0], sm["ymax"]
    return {"diffs": {first + j: v for j, v in enumerate(y)}, "n": len(y)}


def trace_still_runs(trace):
    """Every run of identical scene-graph hashes of 2+ frames, in seconds (the exact reference the delivered file is compared with)."""
    h = trace.get("stateHashes")
    if not h:
        return None
    k = trace.get("hashChars", 12)
    hs = [h[i:i + k] for i in range(0, len(h), k)]
    fps, f0 = trace["fps"], trace["range"][0]
    out, i = [], 0
    while i < len(hs):
        j = i
        while j + 1 < len(hs) and hs[j + 1] == hs[i]:
            j += 1
        if j > i:
            out.append(((f0 + i) / fps, (f0 + j + 1) / fps))
        i = j + 1
    return out


def eval_freeze(rep, cid, ev, allow, what, slop=0.0, extra="", perceptual=False):
    """Stillness is tolerated only inside a hold (declared) or a rest (the plan schedules nothing, short); nothing else.
    perceptual=True is for the delivered file, where a "still span" means nothing visible changes (not that two states are identical):
    the tail of a slow ease is then invisible for a moment even while the plan schedules motion, so a span no longer than a rest
    (allow.restMaxS) is accepted anywhere, and anything longer still needs a declared hold. Exact freezes inside scheduled motion
    are caught separately, on the scene graph (freeze.source), and inside transitions by qa_motion.py."""
    tol = allow.get("tolS", 0.08) + slop
    wins = allow.get("freeze", [])
    holds = [(w["fromS"], w["toS"]) for w in wins if w["kind"] == "hold"]
    rests = [(w["fromS"], w["toS"], w.get("maxS", 1.2) + 2 * slop) for w in wins if w["kind"] == "rest"]
    blacks = [(w["fromS"], w["toS"]) for w in allow.get("black", [])]
    bad = []
    for e0, e1 in ev:
        if contained((e0, e1), holds, tol) or contained((e0, e1), blacks, tol):
            continue
        if any(e0 >= r0 - tol and e1 <= r1 + tol and (e1 - e0) <= mx + allow.get("tolS", 0.08) for r0, r1, mx in rests):
            continue
        if perceptual and (e1 - e0) <= allow.get("restMaxS", 1.2) + allow.get("tolS", 0.08):
            continue
        scheduled = [m for m in allow.get("scheduledMotionS", []) if min(e1, m[1]) - max(e0, m[0]) > 0.15]
        bad.append((e0, e1, "STALL: the plan schedules motion here" if scheduled else "stillness longer than a rest and not a declared hold"))
    sfx = f"; {extra}" if extra else ""
    if bad:
        rep.add(cid, "fail", len(bad), "unplanned stillness in " + what + " at " + "; ".join(f"{x:.2f}-{y:.2f}s ({why})" for x, y, why in bad[:5]) + sfx)
    else:
        rep.add(cid, "pass", len(ev), (f"{len(ev)} still span(s) in {what}, all declared holds or planned rests" if ev else f"{what} never holds still long enough to matter") + sfx)


# ───────────────────────────── audio gates ─────────────────────────────
def audio_gates(rep, a, au, dur, allow, th, fault, selfcheck_ok, plan):
    af = f'silencedetect=n={th["silence"]["noiseDb"]}dB:d={th["silence"]["minS"]},ebur128=peak=true:framelog=verbose'
    if "bad_audio_filter" in fault:
        af += ",nosuchaudiofilter=x=1"
    r = run_tool(["ffmpeg", "-nostdin", "-loglevel", "level+verbose", "-i", a.file, "-map", "0:a:0", "-af", af, "-vn", "-f", "null", "-"])
    if r.rc != 0 or r.fatal_lines():
        cause = f"the audio analysis pass failed (exit {r.rc}): {(r.fatal_lines() or [r.tail()])[0]}"
        rep.blocked("silence", cause, r)
        rep.blocked("loudness", cause, r)
    else:
        adur = float(au.get("duration") or dur)
        L = parse_loudness(r.err)
        if L["lastT"] is None or L["lastT"] < adur - 1.0:
            cause = f"loudness analysis covers {L['lastT']} s of {adur:.1f} s of audio"
            rep.blocked("silence", cause, r)
            rep.blocked("loudness", cause, r)
        elif not selfcheck_ok:
            rep.blocked("silence", "the detectors did not pass their self-check")
            rep.blocked("loudness", "the detectors did not pass their self-check")
        else:
            ev = parse_silence(r.err, adur)
            atol = (allow or {}).get("audioTolS", 0.06)
            wins = [(w["fromS"], w["toS"]) for w in (allow or {}).get("silence", [])]
            bad = [e for e in ev if not contained(e, wins, atol)]
            if bad:
                rep.add("silence", "fail", len(bad), f"unplanned silence (dead air) at {fmt_iv(bad)}; the assembly records silences only at {fmt_iv(wins) or 'no place'}")
            else:
                rep.add("silence", "pass", len(ev), f"{len(ev)} silence(s) of {th['silence']['minS']} s or more, all recorded by the assembly" if ev else f"no silence of {th['silence']['minS']} s or more")
            if L["I"] is None or L["TP"] is None:
                rep.blocked("loudness", "the ebur128 summary could not be parsed", r)
            else:
                T = th["loudness"]
                ok = abs(L["I"] - T["targetLufs"]) <= T["toleranceLu"] and L["TP"] <= T["maxTruePeakDbtp"]
                rep.add("loudness", "pass" if ok else "fail", {"integratedLufs": L["I"], "lra": L["LRA"], "truePeakDbtp": L["TP"]}, f'engineering target {T["targetLufs"]}±{T["toleranceLu"]} LUFS, true peak ≤ {T["maxTruePeakDbtp"]} dBTP (calibrate by ear and against the channel; not a YouTube requirement)')
    narration_gate(rep, a, plan, th, allow)
    sync_gate(rep, a, plan, th)


def narration_gate(rep, a, plan, th, allow):
    """Words the alignment says are spoken must not sit in silence: catches a muted, dropped or misplaced narration span."""
    if not plan or not plan.get("words"):
        rep.add("narration", "info", None, "no plan words supplied; the narration-span check was not run")
        return
    try:
        x = decode_mono(a.file, 16000)
    except Exception as e:  # noqa: BLE001
        rep.add("narration", "blocked", None, f"could not decode the audio for the narration check: {e}")
        return
    hop = 160
    n = len(x) // hop
    e = 10 * np.log10(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    loud = e[e > np.percentile(e, 60)]
    med = float(np.median(loud)) if len(loud) else float(np.median(e))
    floor = med - th["narration"]["silentBelowDbOfMedian"]
    silent = []
    for w in plan["words"]:
        i0, i1 = int(w["s"] * 100), max(int(w["e"] * 100), int(w["s"] * 100) + 1)
        seg = e[i0:i1]
        if len(seg) and seg.max() < floor:
            silent.append(w)
    runs, cur = [], []
    for w in plan["words"]:
        if w in silent:
            cur.append(w)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    wins = [(s["fromS"], s["toS"]) for s in (allow or {}).get("silence", [])]
    bad = [r for r in runs if (len(r) >= th["narration"]["minWords"] or r[-1]["e"] - r[0]["s"] >= th["narration"]["minS"]) and not contained((r[0]["s"], r[-1]["e"]), wins, 0.06)]
    if bad:
        rep.add("narration", "fail", len(bad), "narration is silent where words are aligned: " + "; ".join(f"{r[0]['s']:.2f}-{r[-1]['e']:.2f}s “{' '.join(w['w'] for w in r[:6])}”" for r in bad[:4]))
    else:
        rep.add("narration", "pass", len(plan["words"]), f"all {len(plan['words'])} aligned words carry speech energy (speech median {med:.0f} dBFS, floor {floor:.0f})")


def sync_gate(rep, a, plan, th):
    master = a.master or (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(a.plan))), plan["audio"]["file"]) if plan and plan.get("audio") and a.plan else None)
    if not master or not os.path.exists(master):
        rep.add("sync", "info", None, "no master audio supplied or found; audio offset against the master was not measured")
        return
    try:
        sr = 8000
        x, y = decode_mono(a.file, sr), decode_mono(master, sr)
    except Exception as e:  # noqa: BLE001
        rep.add("sync", "blocked", None, f"could not decode audio for the offset check: {e}")
        return
    hop = 80
    env = lambda z: np.log10(np.sqrt(np.mean(z[: (len(z) // hop) * hop].reshape(-1, hop) ** 2, axis=1)) + 1e-6)  # noqa: E731
    ex, ey = env(x), env(y)
    n = min(len(ex), len(ey), 6000)
    ex, ey = ex[:n] - ex[:n].mean(), ey[:n] - ey[:n].mean()
    max_lag = 50  # ±0.5 s at 10 ms hops
    best = max(range(-max_lag, max_lag + 1), key=lambda k: float(np.dot(ex[max(k, 0): n + min(k, 0)], ey[max(-k, 0): n - max(k, 0)])) / max(n - abs(k), 1))
    lag = best * 0.01
    ok = abs(lag) <= th["sync"]["maxLagS"]
    rep.add("sync", "pass" if ok else "fail", round(lag, 3), f"the audio in the file is offset {lag * 1000:+.0f} ms from {os.path.basename(master)} (max ±{th['sync']['maxLagS'] * 1000:.0f} ms)")


# ───────────────────────────── contact sheets ─────────────────────────────
def make_sheets(rep, a, kind, allow, dur):
    os.makedirs(os.path.dirname(a.sheets) or ".", exist_ok=True)
    every = a.every or (5.0 if kind == "long" else 1.5)
    width, tile = (320, "6x4") if kind == "long" else (216, "8x2")
    sheets = []
    r = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", a.file, "-vf", f"fps=1/{every},scale={width}:-2,tile={tile}:padding=4:margin=4:color=black", "-q:v", "4", f"{a.sheets}_sheet_%02d.jpg"])
    d_, pre = os.path.dirname(a.sheets) or ".", os.path.basename(a.sheets) + "_sheet_"
    per = int(tile.split("x")[0]) * int(tile.split("x")[1])
    files = sorted(x for x in os.listdir(d_) if x.startswith(pre))
    if r.rc != 0 or not files:
        rep.add("sheets", "blocked", None, f"contact sheets were not produced: {r.tail()}")
        return sheets
    for f in files:
        n = int(re.search(r"_(\d+)\.jpg$", f).group(1))
        sheets.append({"file": os.path.join(d_, f), "startS": (n - 1) * per * every, "everyS": every, "tile": tile})
    for k, t in enumerate(((allow or {}).get("sampleTimesS") or [])[:12]):
        out = f"{a.sheets}_risk_{k:02d}_{t:.1f}s.jpg"
        rr = run_tool(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", str(max(t - 0.6, 0)), "-t", "1.2", "-i", a.file, "-vf", f"fps=5,scale={width}:-2,tile=6x1:padding=4:margin=4:color=black", "-frames:v", "1", "-q:v", "4", out])
        if rr.rc == 0 and os.path.exists(out):
            sheets.append({"file": out, "aroundS": t, "frames": "6 frames across 1.2s"})
    rep.add("sheets", "info", len(sheets), "view these with Read; contact-sheet tile n covers startS + n*everyS")
    return sheets


if __name__ == "__main__":
    sys.exit(main())
