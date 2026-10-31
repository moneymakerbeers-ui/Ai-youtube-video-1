#!/usr/bin/env python3
"""assemble_audio.py - join the narration takes of the LONG video into audio/narration.wav with recorded silences.

usage: python tools/assemble_audio.py --scenes scenes.json --takes audio/takes.json --out audio/narration.wav --assembly audio/assembly.json
takes.json: [{"takeId": "t01", "file": "audio/takes/t01.wav", "sceneIds": ["s01","s02"]}, ...]  in playing order; together the
takes cover every scene exactly once, in scene order. A declared pause (pauseAfterMs of the previous scene + pauseBeforeMs of
the next) is only possible at a take boundary, so stage 03 must start a new take wherever a pause is declared (this tool
rejects a pause declared INSIDE a take rather than ignoring it).
Writes narration.wav (mono, 24 kHz) and assembly.json: {audio:{file,sha256,durationS,sr}, segments:[{id,startS,endS,sceneIds}],
silences:[{fromS,toS,reason,declaredMs}]}.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio_lib import BASE_GAP_MS, SR, assemble, load, trim_voiced  # noqa: E402
from common import die, duration_s, read_json, sha256_file, write_json, write_wav  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--takes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--assembly", required=True)
    ap.add_argument("--project", default=".")
    a = ap.parse_args()
    sc = read_json(a.scenes)
    order = [s["id"] for s in sc["scenes"]]
    by = {s["id"]: s for s in sc["scenes"]}
    takes = read_json(a.takes)
    flat = [sid for t in takes for sid in t["sceneIds"]]
    if flat != order:
        die(f"takes must cover the scenes exactly once and in order.\n  scenes: {order}\n  takes:  {flat}")
    # a declared pause inside a take cannot be honoured
    for t in takes:
        ids = t["sceneIds"]
        for p, q in zip(ids, ids[1:]):
            declared = by[p]["voice"].get("pauseAfterMs", 0) + by[q]["voice"].get("pauseBeforeMs", 0)
            if declared > 0:
                die(f"scenes {p} and {q} declare a {declared} ms pause but share take {t['takeId']}; split the take between them")
    parts = []
    for k, t in enumerate(takes):
        if not os.path.exists(os.path.join(a.project, t["file"])):
            die(f"take file missing: {t['file']}")
        x = trim_voiced(load(os.path.join(a.project, t["file"])))
        part = {"id": t["takeId"], "x": x, "meta": {"sceneIds": t["sceneIds"]}}
        if k:
            prev_last = takes[k - 1]["sceneIds"][-1]
            declared = by[prev_last]["voice"].get("pauseAfterMs", 0) + by[t["sceneIds"][0]]["voice"].get("pauseBeforeMs", 0)
            part.update({"gapBeforeMs": BASE_GAP_MS + declared, "declaredMs": declared, "reason": "declared pause" if declared else "take join"})
        parts.append(part)
    lead, tail = sc.get("opening", {}).get("leadSilenceMs", 0), sc.get("ending", {}).get("tailSilenceMs", 0)
    audio, segments, silences = assemble(parts, lead, tail)
    write_wav(a.out, audio, SR)
    write_json(a.assembly, {"audio": {"file": os.path.relpath(a.out, a.project), "sha256": sha256_file(a.out), "durationS": round(duration_s(a.out), 3), "sr": SR}, "segments": segments, "silences": silences})
    print(f"assembled {len(takes)} takes into {a.out} ({duration_s(a.out):.1f}s), {len(silences)} recorded silences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
