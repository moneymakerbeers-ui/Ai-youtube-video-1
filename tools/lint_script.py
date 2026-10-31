#!/usr/bin/env python3
"""lint_script.py - fast text checks before any money or render time is spent (stage 01 and stage 03).

usage:
  python tools/lint_script.py --scenes videos/<slug>/scenes.json --facts videos/<slug>/facts.json
         [--shorts videos/<slug>/shorts.json] [--config videos/<slug>/config.json] [--wpm 150] [--min-seconds 300]
exit code: 0 = no FAIL, 1 = at least one FAIL. WARN lines are judgement calls for you to read.
These are heuristics that catch common slips; they do not prove the script is true or good.
"""
import argparse, json, re, sys

HYPE = ["mind-blowing", "mind blowing", "you won't believe", "you wont believe", "shocking", "insane", "unbelievable", "game-changer", "game changer", "incredible", "amazing", "jaw-dropping"]
HEDGES = ["may ", "might ", "could ", "some researchers", "some historians", "some scientists", "evidence suggests", "appears to", "is debated", "scholars disagree", "researchers disagree", "one explanation", "one theory", "probably", "likely"]
BACKWARD = [r"^(this|that|these|those|it|they|he|she|there|so|but|and|also|then|however)\b", r"\bas we (saw|said|discussed|learned|mentioned)\b", r"\bearlier\b", r"\bpreviously\b", r"\blast time\b", r"\bin the (last|previous|next) (chapter|section|part)\b", r"\bremember\b", r"\blike i said\b", r"\bas i said\b"]
CONTROL = [r"\[[^\]]+\]", r"<[^>]+>", r"\((pause|beat|sigh|whisper|laugh)[^)]*\)", r"\*\*|__|^#"]
BIGNUM = r"\d|\b(hundred|thousand|million|billion|trillion|percent|per cent)\b"


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--facts", required=True)
    ap.add_argument("--shorts")
    ap.add_argument("--config")
    ap.add_argument("--wpm", type=float, default=150)
    ap.add_argument("--min-seconds", type=float)
    a = ap.parse_args()
    scenes = json.load(open(a.scenes))["scenes"]
    claims = {c["id"]: c for c in json.load(open(a.facts))["claims"]}
    shorts = json.load(open(a.shorts))["shorts"] if a.shorts else []
    cfg = json.load(open(a.config)) if a.config else {}
    lo, hi = (cfg.get("targetDurationMin") or [5, 15])[:2]
    min_s = a.min_seconds if a.min_seconds is not None else max(lo, 5) * 60
    out = []

    def say(level, where, msg):
        out.append((level, where, msg))

    words_total, pause_total = 0, 0.0
    by_section = {}
    for s in scenes:
        n, text = s["id"], s["narration"]
        words_total += len(text.split())
        v = s.get("voice", {})
        pause_total += (v.get("pauseBeforeMs", 0) + v.get("pauseAfterMs", 0)) / 1000
        by_section.setdefault(s.get("section", "?"), []).append(s.get("retentionBeat"))
        for cid in s.get("claimIds", []):
            c = claims.get(cid)
            if not c:
                say("FAIL", n, f"unknown claim {cid}")
            elif c["status"] == "unverified":
                say("FAIL", n, f"claim {cid} is unverified; cut it or find a source")
            elif c["status"] == "single_source":
                say("WARN", n, f"claim {cid} rests on one source")
            elif c["status"] == "contested" and not any(h in " " + text.lower() + " " for h in HEDGES):
                say("FAIL", n, f"claim {cid} is contested but the narration states it flatly")
        if re.search(BIGNUM, text, re.I) and not s.get("claimIds"):
            say("FAIL", n, "numbers or quantities in the narration but no claim IDs")
        for pat in CONTROL:
            if re.search(pat, text, re.I | re.M):
                say("FAIL", n, f"control tag or markup in spoken text ({pat}); keep directives out of narration")
        for h in HYPE:
            if h in text.lower():
                say("WARN", n, f'hype phrase "{h}"')
        for sent in sentences(text):
            if len(sent.split()) > 28:
                say("WARN", n, f"long sentence ({len(sent.split())} words): {sent[:60]}...")

    first = sentences(scenes[0]["narration"])[0] if scenes else ""
    if len(first.split()) > 20:
        say("WARN", scenes[0]["id"], f"opening sentence is {len(first.split())} words; aim for one concrete, speakable line")
    est = words_total / a.wpm * 60 + pause_total
    if est < min_s:
        say("FAIL", "video", f"estimated {est:.0f}s ({words_total} words at {a.wpm:.0f} wpm + pauses) is under the {min_s:.0f}s minimum; deepen the content, don't pad")
    elif est > hi * 60:
        say("WARN", "video", f"estimated {est:.0f}s exceeds the {hi} minute upper target")
    for sec, beats in by_section.items():
        if not any(b in ("payoff", "settle", "next_question") for b in beats):
            say("WARN", sec, "section has no payoff, settle or next_question beat")

    byid = {s["id"]: s for s in scenes}
    for sh in shorts:
        if sh["status"] != "validated":
            continue
        opening = sh.get("delta", {}).get("openingLine") or (byid.get(sh["sceneIds"][0], {}).get("narration", ""))
        head = " ".join(sentences(opening)[:2]).lower()
        for pat in BACKWARD:
            m = re.search(pat, head if "^" not in pat else sentences(opening)[0].lower() if sentences(opening) else "", re.I)
            if m:
                say("FAIL", sh["id"], f'opening is not independent: "{m.group(0)}" points backwards; write delta.openingLine')
                break
        if len(sentences(opening)) and len(sentences(opening)[0].split()) > 20:
            say("WARN", sh["id"], "opening sentence is long for a Short")

    for level, where, msg in out:
        print(f"{level:4} {where:10} {msg}")
    fails = sum(1 for o in out if o[0] == "FAIL")
    print(f"\n{len(scenes)} scenes, {words_total} words, ~{est:.0f}s estimated; {fails} FAIL, {len(out) - fails} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
