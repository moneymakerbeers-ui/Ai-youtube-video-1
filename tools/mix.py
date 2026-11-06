#!/usr/bin/env python3
"""mix.py - the final audio master of one target: narration (+ optional licensed music bed, ducked) normalised to the loudness target.

usage: python tools/mix.py --project videos/<slug> --target long [--music inputs/music/bed.wav] [--music-db -24] [--lufs -14] [--tp -1.5]
Reads render/plan-<target>.json (audio.file is the aligned narration of THIS target), writes audio/master-<target>.wav (48 kHz stereo pcm)
and audio/mix-<target>.json (measured loudness BEFORE and AFTER, the filter chain, music licence evidence). Timing is never changed:
the master has exactly the narration's duration, so word times and silences recorded by the assembly still hold.

Music: allowed only when <file>.license.json sits next to it (H6: no asset without a logged right). It is looped or trimmed to the
narration length, faded at both ends and ducked under speech by sidechain compression. Without --music the master is the narration alone.
Loudness: two-pass loudnorm (measure, then apply linear gain with the measured values). Engineering target -14 LUFS / -1.5 dBTP; this is
not a YouTube requirement. Exit 3 = BLOCKED (ffmpeg missing / measurement unreadable), 2 = bad input, 4 = the result misses the target.
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import duration_s, read_json, run, sha256_file, write_json  # noqa: E402

SR = 48000


def measure(path_or_graph, kind="file"):
    """Integrated loudness / LRA / true peak through ebur128. Returns dict or raises."""
    r = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", "-i", path_or_graph, "-af", "ebur128=peak=true", "-f", "null", "-"], check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ebur128 failed ({r.returncode}): {r.stderr[-300:]}")
    i = r.stderr.rfind("Summary:")
    s = r.stderr[i:] if i >= 0 else ""
    mi, ml, mp = (re.search(p, s) for p in (r"I:\s+(-?[\d.]+) LUFS", r"LRA:\s+([\d.]+) LU", r"Peak:\s+(-?[\d.]+) dBFS"))
    if not (mi and mp):
        raise RuntimeError("ebur128 summary not found")
    return {"I": float(mi.group(1)), "LRA": float(ml.group(1)) if ml else None, "TP": float(mp.group(1))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--music")
    ap.add_argument("--music-db", type=float, default=-24.0)
    ap.add_argument("--fx", help="a pre-timed effects track (same length as the target), mixed AFTER the music ducking so an impact is not ducked away; needs <file>.license.json")
    ap.add_argument("--fx-db", type=float, default=0.0)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.5)
    ap.add_argument("--tolerance", type=float, default=1.0)
    a = ap.parse_args()
    P = lambda *p: os.path.join(a.project, *p)  # noqa: E731
    plan = read_json(P("render", f"plan-{a.target}.json"))
    if not plan.get("audio"):
        print(f"plan-{a.target} has no audio (estimated-timing preview); nothing to mix", file=sys.stderr)
        return 2
    narr = P(plan["audio"]["file"])
    if not os.path.exists(narr) or sha256_file(narr) != plan["audio"]["sha256"]:
        print("the narration does not match the hash in the plan; re-run alignment and make_plan", file=sys.stderr)
        return 2
    dur = plan["audio"]["durationS"]
    lic = None
    if a.music:
        mp = a.music if os.path.isabs(a.music) else P(a.music)
        lp = mp + ".license.json"
        if not os.path.exists(mp):
            print(f"music file missing: {mp}", file=sys.stderr)
            return 2
        if not os.path.exists(lp):
            print(f"BLOCKED: {mp} has no {os.path.basename(lp)} (name, url, attribution): no asset without a logged right (H6)", file=sys.stderr)
            return 3
        lic = read_json(lp)
    fx_lic = None
    if a.fx:
        fp = a.fx if os.path.isabs(a.fx) else P(a.fx)
        if not os.path.exists(fp):
            print(f"fx file missing: {fp}", file=sys.stderr)
            return 2
        if not os.path.exists(fp + ".license.json"):
            print(f"BLOCKED: {fp} has no {os.path.basename(fp)}.license.json: no asset without a logged right (H6)", file=sys.stderr)
            return 3
        fx_lic = read_json(fp + ".license.json")
    # graph: narration -> [music ducked] -> pad/trim to exactly dur -> loudnorm
    voice = f"[0:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,apad=whole_dur={dur:.6f},atrim=0:{dur:.6f},asetpts=PTS-STARTPTS"
    if a.music:
        g = (f"{voice},asplit=2[v][vsc];[1:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,aloop=loop=-1:size=2147483647,atrim=0:{dur:.6f},"
             f"volume={a.music_db}dB,afade=t=in:d=1.5,afade=t=out:st={max(dur - 2.5, 0):.3f}:d=2.5[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];[v][md]amix=inputs=2:normalize=0:duration=first")
        ins = ["-i", narr, "-i", mp if os.path.isabs(mp) else P(a.music)]
    else:
        g, ins = voice, ["-i", narr]
    if a.fx:
        n = len(ins) // 2
        fxs = f"[{n}:a]aresample={SR},aformat=sample_fmts=fltp:channel_layouts=stereo,apad=whole_dur={dur:.6f},atrim=0:{dur:.6f},asetpts=PTS-STARTPTS,volume={a.fx_db}dB[fxs]"
        g = f"{g}[pre];{fxs};[pre][fxs]amix=inputs=2:normalize=0:duration=first"
        ins = ins + ["-i", a.fx if os.path.isabs(a.fx) else P(a.fx)]
    try:
        pre = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info", *ins, "-filter_complex", g + f",loudnorm=I={a.lufs}:TP={a.tp}:LRA=11:print_format=json[o]", "-map", "[o]", "-f", "null", "-"], check=False)
        if pre.returncode != 0:
            print(f"BLOCKED: the loudness measurement pass failed ({pre.returncode}): {pre.stderr[-300:]}", file=sys.stderr)
            return 3
        j = pre.stderr[pre.stderr.rfind("{"): pre.stderr.rfind("}") + 1]
        m = json.loads(j)
    except Exception as e:  # noqa: BLE001
        print(f"BLOCKED: could not read the loudnorm measurement: {e}", file=sys.stderr)
        return 3
    ln = f"loudnorm=I={a.lufs}:TP={a.tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    out = P("audio", f"master-{a.target}.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *ins, "-filter_complex", f"{g},{ln},aresample={SR}[o]", "-map", "[o]", "-c:a", "pcm_s16le", "-ar", str(SR), "-ac", "2", out], check=False)
    if r.returncode != 0:
        print(f"BLOCKED: the mix pass failed ({r.returncode}): {r.stderr[-300:]}", file=sys.stderr)
        return 3
    try:
        after = measure(out)
    except Exception as e:  # noqa: BLE001
        print(f"BLOCKED: could not measure the mixed master: {e}", file=sys.stderr)
        return 3
    got = duration_s(out)
    ok = abs(after["I"] - a.lufs) <= a.tolerance and after["TP"] <= a.tp + 0.2 and abs(got - dur) <= 0.01
    write_json(P("audio", f"mix-{a.target}.json"), {"target": a.target, "master": os.path.relpath(out, a.project), "sha256": sha256_file(out), "durationS": round(got, 3), "planDurationS": dur, "before": {"I": float(m["input_i"]), "TP": float(m["input_tp"]), "LRA": float(m["input_lra"])}, "after": after, "targetLufs": a.lufs, "targetTruePeak": a.tp, "music": ({"file": a.music, "duckedDb": a.music_db, "license": lic} if a.music else None), "fx": ({"file": a.fx, "db": a.fx_db, "license": fx_lic} if a.fx else None), "ok": ok})
    print(f"master-{a.target}.wav: {got:.2f}s, {m['input_i']} -> {after['I']:.1f} LUFS, true peak {after['TP']:.1f} dBTP, LRA {after['LRA']}" + ("" if ok else "  (MISSES THE TARGET)"))
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
