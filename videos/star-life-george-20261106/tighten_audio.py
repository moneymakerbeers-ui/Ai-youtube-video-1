#!/usr/bin/env python3
"""tighten_audio.py — shorten every pause longer than MAX_GAP in the master narration to KEEP seconds (creator rule: no silent
stretch > 0.4 s). Silence is measured from the audio itself (10 ms RMS frames), never from transcript timestamps, so no speech is cut.
usage: python3 tighten_audio.py narration.mp3 audio/source/narration-tight.wav audio/source/tighten.json"""
import json, subprocess, sys
import numpy as np
SR, MAX_GAP, KEEP, FADE = 44100, 0.40, 0.36, 0.008
src, out, rep = sys.argv[1:4]
x = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout, np.float32).copy()
hop = int(SR * 0.01)
n = len(x) // hop
rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
db = 20 * np.log10(rms)
floor = float(np.percentile(db, 5))
thr = max(-45.0, floor + 8.0)
quiet = db < thr
runs, k = [], 0
while k < n:
    if quiet[k]:
        j = k
        while j < n and quiet[j]:
            j += 1
        runs.append((k, j))
        k = j
    else:
        k += 1
cuts = []
for a, b in runs:
    if a == 0 or b == n:
        continue  # leading/trailing silence is handled by the take trimming
    dur = (b - a) * 0.01
    if dur > MAX_GAP:
        keep_a = a * hop + int((dur - KEEP) / 2 * SR) * 0 + int(KEEP / 2 * SR)
        cut_from = a * hop + int(KEEP / 2 * SR)
        cut_to = b * hop - int(KEEP / 2 * SR)
        cuts.append((cut_from, cut_to, round(dur, 3)))
pieces, pos = [], 0
f = int(FADE * SR)
ramp = np.linspace(1, 0, f, dtype=np.float32)
for c0, c1, _ in cuts:
    seg = x[pos:c0].copy()
    if len(seg) > f:
        seg[-f:] *= ramp
    if pieces or pos > 0:
        if len(seg) > f:
            seg[:f] *= ramp[::-1]
    pieces.append(seg)
    pos = c1
last = x[pos:].copy()
if len(last) > f:
    last[:f] *= ramp[::-1]
pieces.append(last)
y = np.concatenate(pieces)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", out], input=y.tobytes(), check=True)
json.dump({"source": src, "sr": SR, "thresholdDb": round(thr, 1), "noiseFloorDb": round(floor, 1), "maxGapS": MAX_GAP, "keptS": KEEP,
           "cuts": [{"atS": round(c0 / SR, 3), "removedS": round((c1 - c0) / SR, 3), "originalGapS": d} for c0, c1, d in cuts],
           "durationBeforeS": round(len(x) / SR, 3), "durationAfterS": round(len(y) / SR, 3)}, open(rep, "w"), indent=1)
print(f"{len(cuts)} pauses shortened; {len(x)/SR:.2f}s -> {len(y)/SR:.2f}s (threshold {thr:.1f} dBFS, floor {floor:.1f})")
