#!/usr/bin/env python3
"""short_audio.py - build the COMPLETE final audio timeline of one Short, then measure it again.

A Short may open or close with its own lines and may reorder or skip material, so the parent's word timestamps are wrong for
it. This tool assembles the Short's real narration (opening line + slices of the long narration + closing line, with recorded
silences), writes its own script, and runs the aligner on THAT assembled file. The result in audio/shorts/<id>/ is what the
Short's plan, captions, animation cues and QA use. The parent's timestamps are never copied.

usage: python tools/short_audio.py --project videos/<slug> --short S01 [--engine dtw]
needs: audio/narration.wav + audio/alignment.json (long), shorts.json, scenes.json; audio/shorts/<id>/opening.wav and closing.wav
       when the plan has an opening or closing line (stage 03 step 10 synthesises them in the same voice).
writes (under audio/shorts/<id>/): narration.wav, timeline.json, script-scenes.json, spoken_script.txt, assembly.json, alignment.json
"""
import argparse, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio_lib import BASE_GAP_MS, SR, assemble, load, trim_voiced, voiced_bounds  # noqa: E402
from common import die, duration_s, read_json, sha256_file, write_json, write_wav  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--short", required=True)
    ap.add_argument("--engine", default="auto")
    ap.add_argument("--align-script", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "align.py"))
    a = ap.parse_args()
    P = lambda *p: os.path.join(a.project, *p)  # noqa: E731
    sc = read_json(P("scenes.json"))
    sh = next((s for s in read_json(P("shorts.json"))["shorts"] if s["id"] == a.short), None)
    if not sh:
        die(f"unknown Short {a.short}")
    if sh["status"] != "validated":
        die(f"Short {a.short} is {sh['status']}, not validated")
    al = read_json(P("audio", "alignment.json"))
    parent_audio = P(al["audio"]["file"])
    if sha256_file(parent_audio) != al["audio"]["sha256"]:
        die("the long narration changed after it was aligned; re-run alignment first")
    bounds = {b["sceneId"]: b for b in al["sceneBounds"]}
    idx = {s["id"]: i for i, s in enumerate(sc["scenes"])}
    by = {s["id"]: s for s in sc["scenes"]}
    x_parent = load(parent_audio)
    out = P("audio", "shorts", a.short)
    os.makedirs(out, exist_ok=True)

    parts, script_scenes = [], []
    delta = sh.get("delta", {})

    def line(kind):
        text = delta.get(kind + "Line")
        if not text:
            return
        f = os.path.join(out, f"{kind}.wav")
        if not os.path.exists(f):
            die(f"the plan has an {kind} line but {f} does not exist (stage 03 step 10)")
        parts.append({"id": f"{a.short}_{kind}", "x": trim_voiced(load(f)), "gapBeforeMs": 350, "reason": f"{kind} line join", "meta": {"sceneIds": [f"{a.short}_{kind}"], "kind": kind}})
        script_scenes.append({"id": f"{a.short}_{kind}", "narration": text})

    line("opening")
    prev_sid, prev_end = None, None  # prev_end: where the previous slice ended in the PARENT audio (samples)
    for sid in sh["sceneIds"]:
        if sid not in bounds:
            die(f"scene {sid} has no alignment bounds")
        b = bounds[sid]
        w0, w1 = al["words"][b["firstWord"]], al["words"][b["lastWord"]]
        s0 = int(max(w0["s"] - 0.08, 0) * SR)
        s1 = int(min(w1["e"] + 0.08, al["audio"]["durationS"]) * SR)
        va, vb = voiced_bounds(x_parent[s0:s1])
        a_abs, b_abs = s0 + va, s0 + vb
        gap = BASE_GAP_MS
        if prev_sid is not None and idx[sid] == idx[prev_sid] + 1:
            # neighbours in the long video keep their natural rhythm: the gap is the parent's own pause between the two voiced slices
            # (word timestamps put boundaries inside the pause, so gap = next word start - last word end, plus the trim pads, overstated it;
            #  the slices are contiguous in the parent, so the pause is exactly the long video's pause)
            # take the parent's own pause audio (room tone, breaths) contiguously instead of replacing it with digital silence
            a_abs, gap = prev_end, 0
        elif prev_sid is None and not parts:
            gap = 0
        part = {"id": sid, "x": x_parent[a_abs:b_abs], "meta": {"sceneIds": [sid], "kind": "scene", "srcStartS": round(w0["s"], 3), "srcEndS": round(w1["e"], 3)}}
        prev_end = b_abs
        if parts:
            part.update({"gapBeforeMs": gap, "reason": "scene join", "declaredMs": 0})
        parts.append(part)
        script_scenes.append({"id": sid, "narration": by[sid]["narration"]})
        prev_sid = sid
    line("closing")
    # optional declared lead (room for an opening sound) and end-card hold; both are recorded silences, so the plan and QA know them
    audio, segments, silences = assemble(parts, lead_ms=int(sh.get("leadMs", 0)), tail_ms=int(sh.get("endHoldMs", 0)))
    write_wav(os.path.join(out, "narration.wav"), audio, SR)
    write_json(os.path.join(out, "assembly.json"), {"audio": {"file": os.path.relpath(os.path.join(out, "narration.wav"), a.project), "sha256": sha256_file(os.path.join(out, "narration.wav")), "durationS": round(duration_s(os.path.join(out, "narration.wav")), 3), "sr": SR}, "segments": segments, "silences": silences})
    write_json(os.path.join(out, "script-scenes.json"), {"scenes": script_scenes})
    write_json(os.path.join(out, "timeline.json"), {"short": a.short, "segments": segments, "silences": silences, "note": "assembled from the long narration slices and the Short's own lines; alignment.json measures THIS file"})
    cmd = [sys.executable, a.align_script, "--audio", os.path.join(out, "narration.wav"), "--assembly", os.path.join(out, "assembly.json"), "--scenes", os.path.join(out, "script-scenes.json"), "--script", os.path.join(out, "spoken_script.txt"), "--out", os.path.join(out, "alignment.json"), "--engine", a.engine, "--project", a.project]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"alignment of the assembled Short failed (exit {r.returncode})", file=sys.stderr)
        return r.returncode
    print(f"Short {a.short}: {duration_s(os.path.join(out, 'narration.wav')):.1f}s of its own audio, aligned on the assembled file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
