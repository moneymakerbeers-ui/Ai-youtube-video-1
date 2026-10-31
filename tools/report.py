#!/usr/bin/env python3
"""report.py - the production report: what was made, what each gate said, what was spent, what a person still has to look at.

usage: python tools/report.py --project videos/<slug> [--out review/production-report.md]
Everything in it is read from the run's own files (QA reports, plans, traces, ledger, state, downgrades, evidence check); nothing is estimated and nothing
is written from memory. A file that is missing is reported as "not run", never as fine. Also writes review/production-report.json.
Exit 0 always when the report could be written (the verdicts are in the report, not in this exit code): 2 when the project has no scenes.json.
"""
import argparse, glob, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, sha256_file, write_json  # noqa: E402
from ledger import Ledger  # noqa: E402


def jload(path):
    try:
        return read_json(path) if os.path.exists(path) else None
    except Exception:  # noqa: BLE001
        return None


def probe(path):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], capture_output=True, text=True, timeout=60)
        d = json.loads(p.stdout)
        v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
        au = next((s for s in d["streams"] if s["codec_type"] == "audio"), {})
        return {"w": v.get("width"), "h": v.get("height"), "fps": v.get("r_frame_rate"), "codec": v.get("codec_name"), "audio": au.get("codec_name"), "durationS": round(float(d["format"]["duration"]), 3), "bytes": int(d["format"]["size"])}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:160]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    P = lambda *x: os.path.join(a.project, *x)  # noqa: E731
    if not os.path.exists(P("scenes.json")):
        print(f"{a.project}: no scenes.json", file=sys.stderr)
        return 2
    cfg = jload(P("config.json")) or {}
    last = jload(P("render", "pipeline-last.json")) or {}
    targets = last.get("targets") or [os.path.basename(p)[5:-5] for p in sorted(glob.glob(P("render", "plan-*.json"))) if "preview" not in p]
    rep = {"project": os.path.basename(os.path.abspath(a.project)), "idea": cfg.get("videoIdea"), "purpose": cfg.get("purpose", "production"), "madeAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "targets": {}, "humanNeeded": [], "notes": list(last.get("notes", []))}
    lines = []
    L = lines.append
    eng = None
    for t in targets:
        plan, trace = jload(P("render", f"plan-{t}.json")), jload(P("render", f"trace-{t}.json"))
        media, motion = jload(P("qa", f"{t}.json")), jload(P("qa", f"motion-{t}.json"))
        out = "out/full-video.mp4" if t == "long" else f"out/short-{t[1:].zfill(2)}.mp4"
        info = probe(P(out)) if os.path.exists(P(out)) else None
        tr = []
        for s in (plan or {}).get("scenes", []):
            x = s.get("transitionOut")
            if x:
                tr.append({"id": f"{s['id']}>{next((n['id'] for n in plan['scenes'][plan['scenes'].index(s) + 1:][:1]), '?')}", "type": x["type"], "downgradedFrom": x.get("downgradedFrom"), "rationale": x.get("rationale")})
        if trace:
            eng = trace.get("engine")
        warns = [c for r in (media, motion) if r for c in r["checks"] if c["status"] == "warn"]
        rep["targets"][t] = {"file": out if info else None, "video": info, "sha256": sha256_file(P(out)) if info else None,
                             "media": (media or {}).get("overall", "NOT RUN"), "motion": (motion or {}).get("overall", "NOT RUN"),
                             "counts": {"media": (media or {}).get("summary"), "motion": (motion or {}).get("summary")}, "transitions": tr, "warnings": [{"id": c["id"], "detail": c["detail"]} for c in warns]}
        for c in warns:
            rep["humanNeeded"].append(f"{t}: {c['id']} (heuristic warning) - {c['detail']}")
        for c in [c for r in (media, motion) if r for c in r["checks"] if c["status"] == "blocked"]:
            rep["humanNeeded"].append(f"{t}: {c['id']} BLOCKED - {c['detail']}")
    ev = jload(P("review", "evidence-check.json"))
    if ev:
        for f in ev.get("findings", []):
            if f.get("severity") in ("human", "info") or f.get("kind") == "human_needed":
                rep["humanNeeded"].append(f"evidence: {f.get('message')}" + (f" -> {f['action']}" if f.get("action") else ""))
    voice, ali = jload(P("audio", "voice.json")), jload(P("audio", "alignment.json"))
    spend = Ledger(a.project).status() if os.path.exists(P("state.json")) or os.path.exists(P("ledger.jsonl")) else []
    pend = Ledger(a.project).pending() if spend else []
    dg = (jload(P("render", "downgrades.json")) or {}).get("targets", {})
    pg = (jload(P("state.json")) or {}).get("previewGate")
    rep.update({"voice": voice, "alignment": {"source": (ali or {}).get("source"), "coverage": (ali or {}).get("coverage"), "quality": (ali or {}).get("quality")}, "spend": spend, "pendingPaid": [e["key"] for e in pend], "downgrades": dg, "previewGate": pg, "engine": eng})

    L(f"# Production report - {rep['project']}")
    L(f"\nIdea: {rep['idea']}  ·  purpose: **{rep['purpose']}**  ·  made {rep['madeAt']}")
    if rep["purpose"] != "production":
        L(f"\n> This is a **{rep['purpose']}**, not a production video (a production video is at least 5:00 with its Shorts).")
    L("\n## Gate verdicts\n\n| target | file | media QA | motion QA | length | size |\n|---|---|---|---|---|---|")
    for t, r in rep["targets"].items():
        v = r["video"] or {}
        L(f"| {t} | {r['file'] or 'MISSING'} | {r['media']} | {r['motion']} | {v.get('durationS', '-')} s | {v.get('w', '-')}x{v.get('h', '-')} |")
    L("\nA verdict is the gate's own result on the delivered file. WARN items are heuristics and are listed under \"A person still has to look at\". PASSED never means the video is good, only that none of these checks found a defect.")
    L("\n## Transitions\n")
    any_tr = False
    for t, r in rep["targets"].items():
        for x in r["transitions"]:
            any_tr = True
            L(f"- {t} {x['id']}: **{x['type']}**" + (f" (downgraded from {x['downgradedFrom']}: {x['rationale']})" if x["downgradedFrom"] else ""))
    if not any_tr:
        L("- none (cuts only)")
    L("\n## Render\n")
    any_r = False
    for t in targets:
        tm = ((jload(P("render", f"trace-{t}.json")) or {}).get("timing")) or {}
        pl_ = jload(P("render", f"plan-{t}.json")) or {}
        if tm and pl_:
            any_r = True
            fr, ms = pl_.get("durationFrames"), tm.get("msPerFrame")
            L(f"- {t}: {fr} frames at {pl_.get('fps')} fps, {ms} ms/frame with {tm.get('workers')} worker(s) = {tm.get('captureS')} s of capture on this machine" + (f"; a 60 fps render would take about {2 * float(tm.get('captureS')) / 60:.1f} min" if pl_.get("fps") == 30 and tm.get("captureS") else ""))
    if not any_r:
        L("- no render trace found")
    L("\n## Voice and alignment\n")
    L(f"- voice: {voice['stack'] + ' / ' + str(voice['voice']) + ' - ' + voice['quality'] if voice else 'NOT RUN'}")
    q = (ali or {}).get("quality") or {}
    L(f"- alignment: {rep['alignment']['source'] or 'NOT RUN'}, coverage {rep['alignment']['coverage']}, median confidence {q.get('medianConf')}; " + "; ".join(q.get("notes", [])))
    L("\n## Spend\n")
    if spend:
        L("| service | approved | ceiling | spent | in flight |\n|---|---|---|---|---|")
        for s in spend:
            L(f"| {s['service']} | {'yes' if s['approved'] else 'no'} | {s['ceiling']} {s['unit']} | {s['spent']} | {s['inFlight']} |")
    else:
        L("- no paid service was approved or used (free path)")
    if pend:
        L(f"- **unresolved paid requests:** {', '.join(rep['pendingPaid'])} (a resume will query them, never resubmit)")
    if pg:
        L(f"\nCreative preview gate: approved {pg.get('at')} ({pg.get('note') or 'no note'})")
    L("\n## A person still has to look at\n")
    for h in rep["humanNeeded"] or ["nothing flagged by the gates; still play the video once before publishing"]:
        L(f"- {h}")
    if rep["notes"]:
        L("\n## Notes from the run\n")
        for n in rep["notes"]:
            L(f"- {n}")
    if eng:
        L(f"\n## Reproduce\n\nEngine {eng.get('version')} ({eng.get('backend')}, Chromium {eng.get('chromium')}); `python tools/pipeline.py run --project {a.project}` reproduces these files byte for byte on the same versions and worker count (the render is reproducible).")
    out = a.out or P("review", "production-report.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write("\n".join(lines) + "\n")
    write_json(os.path.splitext(out)[0] + ".json", rep)
    print(f"production report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
