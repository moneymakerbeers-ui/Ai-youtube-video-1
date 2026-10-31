#!/usr/bin/env python3
"""new_project.py - create an empty project folder for `/make <VIDEO_IDEA>`.

  python tools/new_project.py --idea "How tunnels through the Earth would really work" [--slug earth-tunnel] [--purpose production|test_clip]
                              [--dir videos] [--max-higgsfield-credits 15] [--language en-US]

Creates videos/<slug>/ with config.json (idea, purpose, spend ceilings, previewGate "required"), state.json, style-tokens.json (the neutral default
look; stage 02 replaces it with the video's own), library -> ../../library, and the working folders. scenes.json, facts.json and shorts.json are
written by stages 01 and 03-05; until then `pipeline.py` reports exactly which of them is missing.
Exit 0 created · 1 the folder already exists (nothing is overwritten) · 2 bad input.
"""
import argparse, json, os, re, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import write_json  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:48].rstrip("-")) or "video"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--idea", required=True)
    ap.add_argument("--slug")
    ap.add_argument("--purpose", default="production", choices=["production", "test_clip"])
    ap.add_argument("--dir", default="videos")
    ap.add_argument("--language", default="en-US")
    ap.add_argument("--max-higgsfield-credits", type=float, default=15)
    ap.add_argument("--duration-min", default=None, help="MIN,MAX minutes (default 6,9 for production, 0.75,1.25 for test_clip)")
    a = ap.parse_args()
    if len(a.idea.strip()) < 3:
        print("the video idea is too short", file=sys.stderr)
        return 2
    slug = a.slug or slugify(a.idea)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slug):
        print("invalid --slug: use only lowercase letters, digits, hyphens and underscores (no paths)", file=sys.stderr)
        return 2
    if not (0 <= a.max_higgsfield_credits <= 100000):
        print("invalid credit budget", file=sys.stderr)
        return 2
    root = os.path.join(REPO, a.dir) if not os.path.isabs(a.dir) else a.dir
    P = os.path.join(root, slug)
    if os.path.exists(P):
        print(f"{P} already exists; nothing was overwritten (use `/make resume` to continue it)", file=sys.stderr)
        return 1
    try:
        lo, hi = map(float, (a.duration_min or ("6,9" if a.purpose == "production" else "0.75,1.25")).split(","))
    except (ValueError, TypeError):
        print("duration must be MIN,MAX in minutes", file=sys.stderr)
        return 2
    if not (0 < lo <= hi <= 180):
        print("invalid duration range: require 0 < MIN <= MAX <= 180", file=sys.stderr)
        return 2
    for d in ("research/sources", "audio", "assets", "review", "render", "out", "qa", "visuals"):
        os.makedirs(os.path.join(P, d))
    cfg = {"videoIdea": a.idea.strip(), "purpose": a.purpose, "language": a.language, "targetDurationMin": [lo, hi], "previewGate": "required",
           "maxPaidSpend": {"higgsfieldCredits": a.max_higgsfield_credits, "elevenlabsChars": None, "otherUsd": 0}, "shortsTarget": [4, 5] if a.purpose == "production" else [1, 1]}
    write_json(os.path.join(P, "config.json"), cfg)
    write_json(os.path.join(P, "state.json"), {"slug": slug, "idea": a.idea.strip(), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "stages": {}, "spendGate": {"status": "not_reached", "services": {}},
                                              "ledger": {"higgsfieldCredits": 0, "elevenlabsChars": 0, "otherUsd": 0}, "deliverables": {}, "blocked": []})
    shutil.copy(os.path.join(REPO, "examples", "smoke", "style-tokens.json"), os.path.join(P, "style-tokens.json"))
    try:
        os.symlink(os.path.relpath(os.path.join(REPO, "library"), P), os.path.join(P, "library"))
    except OSError:
        shutil.copytree(os.path.join(REPO, "library"), os.path.join(P, "library"))
    print(json.dumps({"project": P, "slug": slug, "purpose": a.purpose, "next": "stage 01: research, facts.json, scenes.json (see .claude/commands/01-research-script.md)"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
