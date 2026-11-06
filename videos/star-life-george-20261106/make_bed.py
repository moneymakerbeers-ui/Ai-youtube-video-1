#!/usr/bin/env python3
"""make_bed.py — the sound bed of each target, made entirely in code (no third-party audio, so the right to use it is ours):
  audio/bed/music-<target>.wav  a slow ambient pad (A minor: Am-F-C-G, 8 s per chord), written 8 dB under the narration (the brief: music -22 LUFS vs voice -14)
                                 (mix.py additionally ducks it under speech by sidechain)
  audio/bed/fx-<target>.wav     soft whooshes on label pops / motion transitions (at least 1.2 s apart) and one low boom on the supernova cut
Reads render/plan-<target>.json for every time, so a re-plan means re-running this. Each file gets a .license.json next to it (H6).
usage: python3 make_bed.py [targets…]   (default: long S01 S02 S03 S04 S05)"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
P = lambda *p: os.path.join(HERE, *p)  # noqa: E731
rng = np.random.default_rng(1054)

def lufs(path):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True, text=True)
    line = [l for l in r.stderr.splitlines() if l.strip().startswith("I:")][-1]
    return float(line.split()[1])

def write(path, y):
    y = np.clip(y, -1, 1).astype(np.float32)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_s16le", path], input=y.tobytes(), check=True)

def reverb(x, secs=3.2, mix=0.45):
    n = int(secs * SR)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-np.linspace(0, 7, n)).astype(np.float32)
    ir /= np.sqrt(np.sum(ir ** 2))
    from scipy.signal import fftconvolve
    wet = fftconvolve(x, ir)[: len(x)]
    return (1 - mix) * x + mix * wet

def pad(dur):
    t = np.arange(int(dur * SR)) / SR
    chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 52, 55, 60], [55, 59, 62, 67]]  # Am F C G (MIDI)
    hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    out = np.zeros((len(t), 2), np.float32)
    seg = 8.0
    for k in range(int(np.ceil(dur / seg)) + 1):
        ch = chords[k % 4]
        st = k * seg - 1.5
        env = np.clip((t - st) / 2.5, 0, 1) * np.clip((st + seg + 3.0 - t) / 2.5, 0, 1)
        env = env ** 1.5
        if not env.any():
            continue
        for i, m in enumerate(ch):
            f = hz(m - 12)
            det = 1 + (i - 1.5) * 0.0012
            w = (np.sin(2 * np.pi * f * det * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t + i) + 0.12 * np.sin(2 * np.pi * 3 * f * det * t)) * env
            pan = 0.35 + 0.1 * i
            out[:, 0] += w * (1 - pan); out[:, 1] += w * pan
        # a very soft high shimmer an octave up, slowly breathing
        sh = np.sin(2 * np.pi * hz(ch[-1] + 12) * t) * env * (0.06 + 0.04 * np.sin(2 * np.pi * 0.07 * t))
        out[:, 0] += sh * 0.6; out[:, 1] += sh * 0.4
    trem = 0.85 + 0.15 * np.sin(2 * np.pi * 0.11 * t)
    out *= trem[:, None]
    from scipy.signal import butter, sosfilt
    sos = butter(2, 1400, "low", fs=SR, output="sos")
    out = sosfilt(sos, out, axis=0).astype(np.float32)
    out = np.stack([reverb(out[:, 0]), reverb(out[:, 1])], axis=1)
    fade = np.clip(t / 1.5, 0, 1) * np.clip((dur - t) / 2.5, 0, 1)
    return (out * fade[:, None]).astype(np.float32)

def whoosh(length=0.42):
    n = int(length * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    from scipy.signal import butter, sosfilt
    tt = np.linspace(0, 1, n)
    y = np.zeros(n, np.float32)
    for lo, hi, w in ((400, 1200, 0.6), (1200, 3500, 0.4)):
        sos = butter(2, [lo, hi], "band", fs=SR, output="sos")
        y += sosfilt(sos, noise) * w
    env = np.sin(np.pi * tt) ** 2 * (0.4 + 0.6 * tt)
    y = (y * env).astype(np.float32)
    return np.stack([y * (1 - 0.3 * tt), y * (0.7 + 0.3 * tt)], axis=1)

def boom(length=1.8):
    n = int(length * SR); t = np.arange(n) / SR
    f = 52 * np.exp(-t * 0.6) + 30
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) * np.exp(-t * 2.4)
    from scipy.signal import butter, sosfilt
    thump = sosfilt(butter(2, 180, "low", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t * 14) * 2.5
    y = (y + thump).astype(np.float32)
    y /= np.max(np.abs(y)) + 1e-9
    return np.stack([y, y], axis=1)

def place(track, clip, at, gain):
    i = int(at * SR)
    if i >= len(track): return
    j = min(len(track), i + len(clip))
    track[i:j] += clip[: j - i] * gain

def make(target):
    plan = json.load(open(P("render", f"plan-{target}.json")))
    dur = plan["durationS"]
    narr = P(plan["audio"]["file"])
    L = lufs(narr)
    os.makedirs(P("audio", "bed"), exist_ok=True)
    # music, normalised 8 dB under the narration (before mix.py's ducking)
    m = pad(dur)
    tmp = P("audio", "bed", f".tmp-{target}.wav"); write(tmp, m); Lm = lufs(tmp); os.remove(tmp)
    m *= 10 ** (((L - 8.0) - Lm) / 20)
    write(P("audio", "bed", f"music-{target}.wav"), m)
    # effects: whooshes on pops and motion transitions, one boom at the supernova
    fx = np.zeros((int(dur * SR), 2), np.float32)
    events = []
    for s in plan["scenes"]:
        for e in s["entities"]:
            if e.get("enterStyle") == "pop" and e["enterS"] > 0.3:
                events.append(("whoosh", max(0.0, e["enterS"] - 0.18)))
        tr = s.get("transitionOut")
        if tr and tr["type"] in ("match_movement", "nested_scale", "depth_through_object"):
            events.append(("whoosh", max(0.0, tr["startS"])))
        if s["id"] == "k3":
            events.append(("boom", s["startS"]))
    events.sort(key=lambda x: x[1])
    last, placed = -9.0, []
    wh_gain = 10 ** (-24 / 20)
    for kind, at in events:
        if kind == "boom":
            place(fx, boom(), at, 10 ** (-9 / 20)); placed.append({"kind": kind, "atS": round(at, 3)})
        elif at - last >= 1.2:
            place(fx, whoosh(), at, wh_gain); last = at; placed.append({"kind": kind, "atS": round(at, 3)})
    write(P("audio", "bed", f"fx-{target}.wav"), fx)
    lic = {"name": "made in code for this project (no third-party audio)", "url": "", "attribution": "none required", "generator": "videos/star-life-george-20261106/make_bed.py"}
    for kind in ("music", "fx"):
        json.dump(lic, open(P("audio", "bed", f"{kind}-{target}.wav.license.json"), "w"), indent=1)
    json.dump({"target": target, "narrationLufs": L, "musicTargetLufs": round(L - 8.0, 1), "events": placed}, open(P("audio", "bed", f"bed-{target}.json"), "w"), indent=1)
    print(f"{target}: {dur:.1f}s, narration {L:.1f} LUFS, music at {L-8:.1f} LUFS (pre-duck), {sum(1 for p in placed if p['kind']=='whoosh')} whooshes, {sum(1 for p in placed if p['kind']=='boom')} boom")

if __name__ == "__main__":
    for t in (sys.argv[1:] or ["long", "S01", "S02", "S03", "S04", "S05"]):
        make(t)
