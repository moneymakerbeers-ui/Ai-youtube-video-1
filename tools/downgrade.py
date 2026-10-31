#!/usr/bin/env python3
"""downgrade.py - after the motion gate FAILED on a complex transition, replace that transition by the safest operator and record why.

usage: python tools/downgrade.py --project P --target long --motion qa/motion-long.json
writes <project>/render/downgrades.json
  {"schema": 1, "targets": {"long": {"s01>s02": {"type": "dissolve", "downgradedFrom": "truthful_morph", "check": "motion.s01>s02.anchor",
                                                  "finding": "<the gate's own words>", "round": 1, "at": "..."}}}}
make_plan.py applies it: the window keeps its place and length, only the operator changes and `downgradedFrom` is written into the plan, the QA
report and the production report. The fallback is never silent and never a pass by itself: pipeline.py then re-plans, re-renders and re-runs the
SAME gates on the result.

exit 0  something was downgraded (re-plan and re-render)
    1  a failing transition has no safer operator (a dissolve that fails is a real defect: a person must look)
    2  usage / unreadable report
    3  the motion report has no failed transition check (nothing to downgrade)
"""
import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, write_json  # noqa: E402

LADDER = {t: "dissolve" for t in ("truthful_morph", "match_geometry", "focus_bridge", "match_movement", "nested_scale", "occlusion_reveal", "depth_through_object")}
MECHANICAL = ("boundary", "exposure", "stall", "pop", "anchor")


def failing(report):
    """{transition id: [(check id, detail)]} for the mechanical transition checks that FAILED."""
    out = {}
    for c in report.get("checks", []):
        parts = c["id"].split(".")
        if c["status"] == "fail" and len(parts) == 3 and parts[0] == "motion" and parts[2] in MECHANICAL:
            out.setdefault(parts[1], []).append((c["id"], c.get("detail") or c.get("msg") or ""))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--motion", required=True)
    ap.add_argument("--media", help="the media QA report (only read to say when it failed for reasons a transition cannot fix)")
    a = ap.parse_args()
    try:
        rep = read_json(a.motion)
    except Exception as e:  # noqa: BLE001
        print(f"cannot read {a.motion}: {e}", file=sys.stderr)
        return 2
    types = {t["id"]: t["type"] for t in rep.get("transitions", [])}
    fails = failing(rep)
    if not fails:
        print("no transition failed the motion gate; nothing to downgrade")
        return 3
    path = os.path.join(a.project, "render", "downgrades.json")
    doc = read_json(path) if os.path.exists(path) else {"schema": 1, "targets": {}}
    mine = doc.setdefault("targets", {}).setdefault(a.target, {})
    changed, stuck = 0, []
    for tid, items in fails.items():
        planned = types.get(tid)
        check, finding = items[0]
        extra = f" (+{len(items) - 1} more failed check{'s' if len(items) > 2 else ''})" if len(items) > 1 else ""
        prev = mine.get(tid)
        orig = (prev or {}).get("downgradedFrom") or planned
        to = LADDER.get(planned)
        if not to:
            stuck.append(f"{tid}: {planned} failed {check}: {finding}{extra}")
            continue
        mine[tid] = {"type": to, "downgradedFrom": orig, "check": check, "finding": finding + extra, "round": (prev or {}).get("round", 0) + 1, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        changed += 1
        print(f"downgrade {tid}: {planned} -> {to} because {check} FAILED: {finding}{extra}")
    if changed:
        write_json(path, doc)
    for s in stuck:
        print(f"CANNOT downgrade {s}\n  no safer operator exists; fix the cause (timing, layout, content) or the video is not ready", file=sys.stderr)
    return 0 if changed else 1


if __name__ == "__main__":
    sys.exit(main())
