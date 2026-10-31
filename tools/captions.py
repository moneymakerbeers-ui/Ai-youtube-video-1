#!/usr/bin/env python3
"""captions.py - export the caption file from the render plan (the same phrases the renderer burns in), never from a second timing source.

usage: python tools/captions.py --plan render/plan-long.json --out out/captions.srt [--vtt out/captions.vtt]
Exit 2 if the plan has no words (nothing to caption)."""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json  # noqa: E402
from plan_lib import to_srt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vtt")
    a = ap.parse_args()
    plan = read_json(a.plan)
    caps = plan.get("captions") or []
    if not caps:
        print("the plan has no caption phrases (no aligned words)", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    srt = to_srt(caps)
    open(a.out, "w", encoding="utf-8").write(srt)
    if a.vtt:
        open(a.vtt, "w", encoding="utf-8").write("WEBVTT\n\n" + srt.replace(",", "."))
    print(f"{len(caps)} caption phrases ({plan['target']}, timing from {plan['timingSource']}) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
