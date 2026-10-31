#!/usr/bin/env python3
"""voice_flite.py - FREE local text-to-speech through ffmpeg's libflite filter (voice stack C).

Honest quality note: this is a flat, robotic voice. It exists so the whole pipeline (takes -> assembly -> alignment ->
captions -> animation -> mix -> QA) can run and be tested with no account and no cost, and as the reference voice of
the local aligner. It supports only what post-processing can give: pace (tempo) and a small pitch offset per
`voice.intensity`. It cannot perform emotion; real narration needs voice stack A or B (ElevenLabs).

usage:
  python tools/voice_flite.py --text "Hello there." --out hello.wav [--voice slt] [--pace steady] [--intensity 0]
  python tools/voice_flite.py --takes audio/takes.json --outdir audio/takes     (takes.json: [{takeId, text, pace, intensity}])
"""
import argparse, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, sha256_text, write_json  # noqa: E402

VOICES = ["kal", "kal16", "awb", "rms", "slt"]
TEMPO = {"slower": 0.9, "steady": 1.0, "faster": 1.1}
PITCH = {0: 1.0, 1: 1.02, 2: 1.04, 3: 1.06}  # a modest lift per intensity step; flite cannot do more


def available():
    r = run(["ffmpeg", "-hide_banner", "-filters"], check=False)
    return r.returncode == 0 and " flite " in r.stdout


def synth(text, out, voice="slt", pace="steady", intensity=0, sr=24000):
    """Write `out` (wav, mono, `sr`). Raises on any failure; never returns a silent or empty file."""
    if voice not in VOICES:
        raise ValueError(f"voice must be one of {VOICES}")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text.strip() + "\n")
        tf = f.name
    try:
        af = []
        tempo, pitch = TEMPO.get(pace, 1.0), PITCH.get(int(intensity), 1.0)
        if tempo != 1.0 or pitch != 1.0:
            af.append(f"rubberband=tempo={tempo}:pitch={pitch}")
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"flite=textfile={tf}:voice={voice}"]
        if af:
            cmd += ["-af", ",".join(af)]
        cmd += ["-ac", "1", "-ar", str(sr), out]
        run(cmd)
    finally:
        os.unlink(tf)
    from common import duration_s

    if duration_s(out) < 0.15:
        raise RuntimeError(f"flite produced an empty file for: {text[:60]!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--out")
    ap.add_argument("--voice", default="slt")
    ap.add_argument("--pace", default="steady", choices=list(TEMPO))
    ap.add_argument("--intensity", type=int, default=0)
    ap.add_argument("--takes")
    ap.add_argument("--outdir")
    a = ap.parse_args()
    if not available():
        print("BLOCKED: ffmpeg was built without libflite (no free local voice here)", file=sys.stderr)
        return 3
    if a.takes:
        import json

        os.makedirs(a.outdir, exist_ok=True)
        for t in json.load(open(a.takes)):
            out = os.path.join(a.outdir, f"{t['takeId']}.wav")
            synth(t["text"], out, a.voice, t.get("pace", "steady"), t.get("intensity", 0))
            print(out)
        return 0
    if not (a.text and a.out):
        ap.error("--text and --out (or --takes and --outdir)")
    synth(a.text, a.out, a.voice, a.pace, a.intensity)
    print(a.out, sha256_text(a.text)[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
