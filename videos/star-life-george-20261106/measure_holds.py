#!/usr/bin/env python3
"""measure_holds.py — the brief's two "nothing happens" numbers, measured per delivered target:
  longest static hold   (a) exact, from the renderer's own trace: the longest run of frames whose picture hash is unchanged (captions,
                            grain and fades excluded, so a still image under changing captions still counts as static);
                        (b) in the delivered mp4: ffmpeg freezedetect (noise -60 dB, each frame against the frame the freeze began on)
  longest silence       (a) voice: the longest gap in the narration track the target was cut from (silencedetect -45 dBFS, >= 0.10 s);
                        (b) the delivered mix (music bed included): silencedetect -50 dBFS
Writes qa/holds-<target>.json and prints one line per target. Exit 1 if a static hold > 4.0 s or a voice gap > 0.40 s is found
(the brief's limits; the declared ending tail is excluded from the voice-gap check and reported separately), 3 if a measurement failed."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *p: os.path.join(HERE, *p)  # noqa: E731
STATIC_MAX, GAP_MAX = 4.0, 0.40


def ff(args):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *args, "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    return r.stderr


def silences(path, db, d=0.10):
    err = ff(["-i", path, "-map", "0:a:0", "-af", f"silencedetect=noise={db}dB:d={d}"])
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    en = [(float(a), float(b)) for a, b in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", err)]
    out = [{"startS": round(s, 3), "endS": round(e, 3), "durS": round(dd, 3)} for s, (e, dd) in zip(st, en)]
    if len(st) > len(en):  # runs to the end of the file
        out.append({"startS": round(st[-1], 3), "endS": None, "durS": None, "toEnd": True})
    return out


def freezes(path):
    err = ff(["-i", path, "-map", "0:v:0", "-vf", "freezedetect=n=-60dB:d=0.5"])
    st = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    du = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", err)]
    return [{"startS": round(s, 3), "durS": round(d, 3)} for s, d in zip(st, du)]


def trace_hold(t, fps):
    tr = json.load(open(P("render", f"trace-{t}.json")))
    k = tr["hashChars"]
    frames = [tr["stateHashes"][i:i + k] for i in range(0, len(tr["stateHashes"]), k)]
    best, cur, start, bstart = 0, 1, 0, 0
    for i in range(1, len(frames)):
        if frames[i] == frames[i - 1]:
            cur += 1
        else:
            cur, start = 1, i
        if cur > best:
            best, bstart = cur, start
    return {"frames": best, "durS": round(best / fps, 3), "startS": round(bstart / fps, 3), "totalFrames": len(frames)}


def main():
    worst = 0
    for t in (sys.argv[1:] or ["long", "S01", "S02", "S03", "S04", "S05"]):
        plan = json.load(open(P("render", f"plan-{t}.json")))
        mp4 = P("out", "full-video.mp4" if t == "long" else f"short-{t[1:].zfill(2)}.mp4")
        narr = P(plan["audio"]["file"])
        try:
            th = trace_hold(t, plan["fps"])
            fz = freezes(mp4)
            vs = silences(narr, -45)
            ms = silences(mp4, -50)
        except Exception as e:  # noqa: BLE001
            print(f"{t}: BLOCKED {e}"); worst = max(worst, 3); continue
        last_word = max(w["e"] for w in plan["words"])
        inner = [s for s in vs if s["startS"] < last_word - 0.05 and s["durS"] is not None]
        tail = [s for s in vs if s not in inner]
        lv = max(inner, key=lambda s: s["durS"], default=None)
        lf = max(fz, key=lambda s: s["durS"], default=None)
        lm = max([s for s in ms if s["durS"] is not None], key=lambda s: s["durS"], default=None)
        ok = th["durS"] <= STATIC_MAX and (lf is None or lf["durS"] <= STATIC_MAX) and (lv is None or lv["durS"] <= GAP_MAX)
        res = {"target": t, "staticHoldTrace": th, "longestFreezeDelivered": lf, "freezesOver0_5s": len(fz),
               "longestVoiceGap": lv, "voiceGapsOver0_10s": len(inner), "endingTail": tail, "longestMixSilence": lm,
               "limits": {"staticS": STATIC_MAX, "voiceGapS": GAP_MAX}, "verdict": "PASSED" if ok else "FAILED"}
        json.dump(res, open(P("qa", f"holds-{t}.json"), "w"), indent=1)
        print(f"{t}: {res['verdict']} · static hold {th['durS']}s at {th['startS']}s (trace), delivered freeze {lf['durS'] if lf else 0}s · "
              f"longest voice gap {lv['durS'] if lv else 0}s{' at ' + str(lv['startS']) + 's' if lv else ''} · mix silence {lm['durS'] if lm else 0}s · tail {tail}")
        worst = max(worst, 0 if ok else 1)
    return worst


if __name__ == "__main__":
    sys.exit(main())
