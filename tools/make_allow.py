#!/usr/bin/env python3
"""make_allow.py - derive what the QA may tolerate from the render plan, and NOTHING else.

v2 allowed black at the end of every file, silence at both ends, a half-pause margin around every boundary and a whole-scene
freeze whenever the camera was empty. Those blanket allowances are gone. Here an event is tolerated only when the plan
names it, with its own time window:

  black    only the opening fade-in (scenes.opening.fadeInMs) and the ending fade/hold (scenes.ending.fadeOutMs + holdBlackMs).
           A file without a declared fade has NO tolerated black: an accidental black tail fails.
  freeze   only (a) an explicit hold (layout.hold, kept by make_plan only for the genuinely still part of the scene), and
           (b) a "rest": a gap in which the plan itself schedules no entrance, exit, camera move or transition. A rest is
           tolerated up to rest.maxS; anything longer needs a declared hold, and a freeze while the plan schedules motion
           is a stall and fails.
  silence  only the silences the assembler recorded (declared pauses, take joins, lead and tail). A silence the audio
           contains but the assembly does not list is dead air and fails.

Every window is verified from the other side by qa_media.py: a declared black/hold/silence that is missing, or an event that
runs past its window, fails too.

usage: python tools/make_allow.py --plan render/plan-long.json [--tokens style-tokens.json] [--thresholds t.json] --out qa/allow-long.json [--check]
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, write_json  # noqa: E402
from plan_lib import picture_region  # noqa: E402

# The windows below are exact. The delivered file is compared with them by qa_media.py, which allows freeze.slopS at the edges of
# an eased move (the last frames of an ease change less than any detector can see); that tolerance lives in the instrument, not here.
DEFAULT_TH = {"rest": {"maxS": 1.2, "minGapS": 0.25}, "exitMs": 300}


def union(ivs, gap=0.0):
    out = []
    for a, b in sorted(ivs):
        if b <= a:
            continue
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def complement(ivs, lo, hi):
    out, cur = [], lo
    for a, b in union(ivs):
        if a > cur:
            out.append([cur, min(a, hi)])
        cur = max(cur, b)
    if cur < hi:
        out.append([cur, hi])
    return [iv for iv in out if iv[1] > iv[0]]


def build_allow(plan, tokens=None, th=None):
    th = {**DEFAULT_TH, **(th or {})}
    fps, dur = plan["fps"], plan["durationS"]
    op, en = plan["opening"], plan["ending"]
    warnings = []
    black = []
    if op.get("fadeInMs", 0) > 0:
        black.append({"fromS": 0.0, "toS": round(op["fadeInMs"] / 1000, 3), "reason": f"opening fade-in from black ({op['fadeInMs']} ms, scenes.opening.fadeInMs)", "mustExist": True})
    tail = (en.get("fadeOutMs", 0) + en.get("holdBlackMs", 0)) / 1000
    if tail > 0:
        black.append({"fromS": round(max(dur - tail, 0), 3), "toS": round(dur, 3), "reason": f"ending fade-out and black hold ({en.get('fadeOutMs', 0)}+{en.get('holdBlackMs', 0)} ms, scenes.ending)", "mustExist": en.get("holdBlackMs", 0) > 0})

    # scheduled motion: everything the plan itself says should change the picture
    sched, per_scene = [], {}
    cuts = []
    scenes = plan["scenes"]
    for i, s in enumerate(scenes):
        mv = []
        if i > 0 and not scenes[i - 1].get("transitionOut"):
            cuts.append(round(s["startS"], 3))
            mv.append([s["startS"] - 0.05, s["startS"] + 0.05])
        for e in s["entities"]:
            if e.get("viaTransition"):
                continue
            if e.get("enterStyle") == "none":
                mv.append([e["enterS"] - 0.05, e["enterS"] + 0.05])
            elif e.get("enterMs", 0) > 0:
                mv.append([e["enterS"], e["enterS"] + e["enterMs"] / 1000])
            if e.get("exitS") is not None:
                mv.append([e["exitS"], e["exitS"] + th["exitMs"] / 1000])
            m = e.get("motion")
            if m and m.get("kind") == "continuous":
                mv.append([m["fromS"], m["toS"]])  # e.g. a wave: the plan says this picture must keep moving, so a stillness here is a stall
        for c in s.get("camera", []):
            mv.append([c["fromS"], c["toS"]])
        if s.get("transitionOut"):
            t = s["transitionOut"]
            mv.append([t["startS"], t["endS"]])
        per_scene[s["id"]] = mv
        sched += mv
    if op.get("fadeInMs", 0) > 0:
        sched.append([0.0, op["fadeInMs"] / 1000])
    if tail > 0:
        sched.append([max(dur - tail, 0), dur])
    sched = union(sched, gap=0.0)

    holds = [{"fromS": s["hold"]["fromS"], "toS": s["hold"]["toS"], "kind": "hold", "reason": s["hold"]["reason"], "scene": s["id"]} for s in scenes if s.get("hold")]
    rests = []
    for s in scenes:
        for a, b in complement(per_scene[s["id"]] + [[0, 0]], s["startS"], s["endS"]):
            # trim by the global schedule too (a neighbour's transition may cover the edge of this scene)
            for a2, b2 in complement(sched, a, b):
                if b2 - a2 >= th["rest"]["minGapS"]:
                    rests.append({"fromS": round(a2, 3), "toS": round(b2, 3), "kind": "rest", "maxS": th["rest"]["maxS"], "scene": s["id"], "reason": "the plan schedules no entrance, exit, camera move or transition here"})
    for r in rests:
        covered = any(h["fromS"] <= r["fromS"] + 0.05 and h["toS"] >= r["toS"] - 0.05 for h in holds)
        if r["toS"] - r["fromS"] > r["maxS"] and not covered:
            warnings.append(f"{r['scene']}: {r['toS'] - r['fromS']:.1f} s ({r['fromS']:.1f}-{r['toS']:.1f}) with nothing scheduled and no hold declared; a static picture here will fail QA (add motion, move an entrance, or declare layout.hold with a reason)")

    silences = [{"fromS": x["fromS"], "toS": x["toS"], "reason": x.get("reason", "recorded silence"), "declaredMs": x.get("declaredMs")} for x in plan.get("silences", [])]
    trans = []
    for s in scenes:
        t = s.get("transitionOut")
        if t:
            nxt = scenes[[x["id"] for x in scenes].index(s["id"]) + 1]["id"]
            trans.append({"id": f"{s['id']}>{nxt}", "type": t["type"], "startS": t["startS"], "endS": t["endS"], "from": s["id"], "to": nxt, "easing": t.get("easing", "standard"), "downgradedFrom": t.get("downgradedFrom")})
    risk = sorted({round((t["startS"] + t["endS"]) / 2, 2) for t in trans})
    return {
        "target": plan["target"], "fps": fps, "durationS": dur, "layout": plan["layout"],
        "tolS": round(1.5 / fps + 0.03, 3), "audioTolS": 0.06, "restMaxS": th["rest"]["maxS"],
        "black": black, "freeze": holds + rests, "silence": silences,
        "transitions": trans, "plannedCutsS": cuts, "sampleTimesS": risk,
        "scheduledMotionS": [[round(a, 3), round(b, 3)] for a, b in sched],
        "pictureRegion": plan["pictureRegion"] if "pictureRegion" in plan else picture_region(tokens, plan["layout"]),
        "warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--tokens")
    ap.add_argument("--thresholds")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true", help="print the plan-level warnings (long unscheduled stillness) and exit 1 if there are any")
    a = ap.parse_args()
    plan = read_json(a.plan)
    tokens = read_json(a.tokens) if a.tokens and os.path.exists(a.tokens) else None
    th = read_json(a.thresholds).get("allow") if a.thresholds and os.path.exists(a.thresholds) else None
    allow = build_allow(plan, tokens, th)
    if a.out:
        write_json(a.out, allow)
    n = lambda k: len(allow[k])  # noqa: E731
    print(f"allow {allow['target']}: black windows {n('black')}, freeze windows {n('freeze')} ({sum(1 for f in allow['freeze'] if f['kind'] == 'hold')} holds), silences {n('silence')}, transitions {n('transitions')}" + (f" -> {a.out}" if a.out else ""))
    for w in allow["warnings"]:
        print("warn:", w)
    return 1 if (a.check and allow["warnings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
