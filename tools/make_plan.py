#!/usr/bin/env python3
"""make_plan.py - derive every time the engine and the QA need, once, into render/plan-<target>.json.

The plan is the single source of timing truth: scene windows, entity entrances, camera moves, transition windows, deliberate
holds, planned silences, words and caption phrases. The renderer reads it; make_allow.py derives the QA allow-list from it;
captions.py exports the SRT from it. Nothing downstream recomputes timing.

usage:
  python tools/make_plan.py --project videos/<slug> --target long [--fps N] [--size WxH] [--auto-fit]
  python tools/make_plan.py --project videos/<slug> --target S01
  python tools/make_plan.py --project videos/<slug> --target preview-long [--scenes s01,s05]   (estimated timing, previews only)
Writes <project>/render/plan-<target>.json. Exit 2 on a problem the author must fix (stale audio hash, overlapping
transitions, an unknown scene, camera moves out of order); with --auto-fit an over-long transition is shortened and noted
in plan.warnings instead.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, read_json, sha256_file, write_json  # noqa: E402
from plan_lib import DEFAULT_MS, RES, caption_chunks, picture_region  # noqa: E402

CLAMPS = {"match_geometry": (1 / 8, 8), "truthful_morph": (1 / 8, 8), "focus_bridge": (0.5, 2)}  # the size-ratio clamp of each locked operator (engine/src/transitions.ts)


def estimate(scenes, fps):
    """Preview-only timing: 2.7 words per second plus declared pauses. Never accepted for a final render."""
    t, words, bounds = 0.0, [], []
    gi = 0
    for s in scenes:
        t += s["voice"].get("pauseBeforeMs", 0) / 1000
        t0 = t
        for w in s["narration"].split():
            words.append({"i": gi, "w": w, "s": round(t, 3), "e": round(t + 0.33, 3), "sceneId": s["id"]})
            gi += 1
            t += 0.37
        t += s["voice"].get("pauseAfterMs", 0) / 1000 + 0.25
        bounds.append({"sceneId": s["id"], "startS": round(t0 - 0.0, 3), "endS": round(t, 3)})
    for k, b in enumerate(bounds):  # contiguous windows
        b["startS"] = 0.0 if k == 0 else bounds[k - 1]["endS"]
    return words, bounds, round(t, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--fps", type=int)
    ap.add_argument("--size", help="WxH override (drafts, previews, tests)")
    ap.add_argument("--visuals", help="render/visuals-manifest.json (which visuals move continuously); default <project>/render/visuals-manifest.json")
    ap.add_argument("--auto-fit", action="store_true")
    ap.add_argument("--scenes", help="preview: comma-separated scene ids to include")
    ap.add_argument("--out")
    a = ap.parse_args()
    P = lambda *p: os.path.join(a.project, *p)  # noqa: E731
    sc = read_json(P("scenes.json"))
    fps = a.fps or sc.get("fps", 30)
    scenes_all = sc["scenes"]
    by = {s["id"]: s for s in scenes_all}
    idx = {s["id"]: i for i, s in enumerate(scenes_all)}
    cfg = read_json(P("config.json")) if os.path.exists(P("config.json")) else {}
    tokens = read_json(P("style-tokens.json")) if os.path.exists(P("style-tokens.json")) else {}
    vm_path = a.visuals or P("render", "visuals-manifest.json")
    vmotion = {}
    if os.path.exists(vm_path):
        vmotion = {k: v.get("motion", "enter") for k, v in read_json(vm_path).get("visuals", {}).items()}
    else:
        print(f"note: {vm_path} not found; no visual is treated as moving continuously (run engine/visuals-manifest.ts, or use tools/pipeline.py which does)", file=sys.stderr)
    max_words = tokens.get("caption", {}).get("maxWords", 7)
    warnings = []
    # operators the motion gate rejected on an earlier render (tools/downgrade.py): applied here, recorded in the plan, never silent
    dg_path = P("render", "downgrades.json")
    downgrades = (read_json(dg_path).get("targets", {}).get(a.target, {})) if os.path.exists(dg_path) else {}

    is_short = bool(a.target.startswith("S") and a.target[1:].isdigit())
    preview = a.target.startswith("preview")
    layout = "portrait" if (is_short or a.target.endswith("portrait")) else "landscape"
    W, H = RES.get(cfg.get("outputResolution", "1080p"), RES["1080p"])
    if a.size:
        W, H = map(int, a.size.lower().split("x"))
    if layout == "portrait" and W > H:
        W, H = H, W

    # ── which scenes, in which order, with which windows and words ──
    audio, silences, timing_source = None, [], "alignment"
    if preview:
        ids = a.scenes.split(",") if a.scenes else [s["id"] for s in scenes_all]
        order = [by[i] for i in ids]
        words, bounds, dur = estimate(order, fps)
        timing_source = "estimated"
    elif is_short:
        sh = next((s for s in read_json(P("shorts.json"))["shorts"] if s["id"] == a.target), None)
        if not sh or sh["status"] != "validated":
            die(f"{a.target} is not a validated Short")
        al_path = P("audio", "shorts", a.target, "alignment.json")
        if not os.path.exists(al_path):
            die(f"{al_path} missing: run tools/short_audio.py first (a Short needs its own aligned audio)")
        al = read_json(al_path)
        audio_path = P(al["audio"]["file"])
        if not os.path.exists(audio_path) or sha256_file(audio_path) != al["audio"]["sha256"]:
            die(f"{a.target}: the assembled audio does not match its alignment hash; re-run short_audio.py")
        asm = read_json(P("audio", "shorts", a.target, "assembly.json"))
        silences = asm["silences"]
        audio = {"file": al["audio"]["file"], "sha256": al["audio"]["sha256"], "durationS": al["audio"]["durationS"]}
        order = [by[i] for i in sh["sceneIds"]]
        # words: opening/closing lines belong to the first / last scene's window
        sb = {b["sceneId"]: b for b in al["sceneBounds"]}
        open_id, close_id = f"{a.target}_opening", f"{a.target}_closing"
        words = []
        for w in al["words"]:
            sid = w.get("scene")
            own = sid if sid in by else (order[0]["id"] if sid == open_id else order[-1]["id"])
            words.append({"i": w["i"], "w": w["w"], "s": w["s"], "e": w["e"], "sceneId": own, "own": sid in by})
        bounds = []
        for k, s in enumerate(order):
            b = sb[s["id"]]
            st = 0.0 if k == 0 else b["startS"]
            en = al["audio"]["durationS"] if k == len(order) - 1 else b["endS"]
            bounds.append({"sceneId": s["id"], "startS": st, "endS": en, "firstWord": b["firstWord"], "lastWord": b["lastWord"]})
        dur = al["audio"]["durationS"]
    else:
        al_path = P("audio", "alignment.json")
        if not os.path.exists(al_path):
            die(f"{al_path} missing: run stage 03 (align) first")
        al = read_json(al_path)
        audio_path = P(al["audio"]["file"])
        if not os.path.exists(audio_path) or sha256_file(audio_path) != al["audio"]["sha256"]:
            die("narration.wav changed after it was aligned (hash mismatch); re-run alignment")
        silences = read_json(P("audio", "assembly.json"))["silences"] if os.path.exists(P("audio", "assembly.json")) else []
        audio = {"file": al["audio"]["file"], "sha256": al["audio"]["sha256"], "durationS": al["audio"]["durationS"]}
        order = scenes_all
        bounds = [dict(b) for b in al["sceneBounds"]]
        if [b["sceneId"] for b in bounds] != [s["id"] for s in order]:
            die("alignment.sceneBounds do not list the scenes in order; re-run alignment with --scenes")
        words = [{"i": w["i"], "w": w["w"], "s": w["s"], "e": w["e"], "sceneId": w.get("scene", "?"), "own": True} for w in al["words"]]
        dur = al["audio"]["durationS"]

    # words belonging to each scene's own narration (enterAtWord / camera word indices are scene-relative)
    own_words = {s["id"]: [w for w in words if w["sceneId"] == s["id"] and w.get("own", True)] for s in order}

    def word_time(sid, k, edge):
        ws = own_words[sid]
        if k >= len(ws):
            die(f"{sid}: word index {k} but the aligned scene has only {len(ws)} words")
        return ws[k]["s" if edge == "s" else "e"]

    # ── transitions: windows centred on boundaries ──
    plan_scenes = []
    prev_window_end = 0.0
    for k, s in enumerate(order):
        b = bounds[k]
        lay = s["layouts"].get(layout) or s["layouts"]["landscape"]
        if layout == "portrait" and not s["layouts"].get("portrait"):
            die(f"{s['id']} has no portrait layout (needed by {a.target})")
        ent = []
        prev_tr = order[k - 1].get("transition", {}) if k else {}
        incoming_anchor = (prev_tr.get("anchorTo") or {}).get("entityId") if (k and prev_tr.get("type", "cut") != "cut" and (not is_short or idx[s["id"]] == idx[order[k - 1]["id"]] + 1)) else None
        for e in s["entities"]:
            if e.get("only") and e["only"] != layout:
                continue  # drawn in the other layout only (e.g. a Short's own title card)
            en_s = word_time(s["id"], e["enterAtWord"], "s") if e.get("enterAtWord") is not None else b["startS"]
            ex_s = word_time(s["id"], e["exitAtWord"], "s") if e.get("exitAtWord") is not None else None
            en = e.get("enter") or {}
            style = en.get("style", "fade")
            ms = en.get("durationMs", tokens.get("motion", {}).get("enterMs", 500))
            rec = {"id": e["id"], "enterS": round(en_s, 3), "exitS": None if ex_s is None else round(ex_s, 3), "enterStyle": style, "enterMs": 0 if style == "none" else int(ms)}
            if e["id"] == incoming_anchor:
                rec["viaTransition"] = True  # the previous scene's transition IS its entrance
                rec["enterMs"] = 0
            comp = (e.get("visual") or {}).get("component")
            if comp and vmotion.get(comp) == "continuous":
                # the picture keeps changing for as long as the entity is on screen (until it exits or the scene ends)
                rec["motion"] = {"kind": "continuous", "fromS": rec["enterS"] + rec["enterMs"] / 1000, "toS": rec["exitS"] if rec["exitS"] is not None else round(b["endS"], 3)}
            ent.append(rec)
        cams, last_to = [], -1
        for ci, cm in enumerate(lay.get("camera", [])):
            f_s = word_time(s["id"], cm["startWord"], "s") if cm.get("startWord") is not None else b["startS"]
            t_s = word_time(s["id"], cm["endWord"], "e") if cm.get("endWord") is not None else b["endS"]
            if t_s <= f_s:
                die(f"{s['id']}: camera move {ci} has no duration")
            if f_s < last_to - 1e-6:
                die(f"{s['id']}: camera move {ci} starts before the previous move ends")
            last_to = t_s
            cams.append({"fromS": round(f_s, 3), "toS": round(t_s, 3), "from": cm["from"], "to": cm["to"], "easing": cm.get("easing", "emphasized")})
        ps = {"id": s["id"], "startS": round(b["startS"], 3), "endS": round(b["endS"], 3), "layout": layout, "entities": ent, "camera": cams}
        if s.get("look"):
            ps["look"] = s["look"]
        if lay.get("shake"):
            sh = lay["shake"]
            f_s = word_time(s["id"], sh["atWord"], "s")
            ps["shake"] = {"fromS": round(f_s, 3), "toS": round(min(f_s + sh.get("durationMs", 600) / 1000, b["endS"]), 3), "amplitude": sh.get("amplitude", 0.012)}
        # outgoing transition (a Short keeps one only between scenes that are neighbours in the long video)
        tr = s.get("transition", {"type": "cut"})
        last = k + 1 >= len(order)
        keep = (not last) and (not is_short or idx[order[k + 1]["id"]] == idx[s["id"]] + 1)
        typ = tr.get("type", "cut") if keep else "cut"
        window = None
        dg = downgrades.get(f"{s['id']}>{order[k + 1]['id']}") if (typ != "cut" and k + 1 < len(order)) else None
        if typ != "cut":
            d = (tr.get("durationMs") or DEFAULT_MS.get(typ, 800)) / 1000  # the window keeps the length of the transition that was planned
            mid = b["endS"] + tr.get("offsetMs", 0) / 1000
            nxt = bounds[k + 1]
            room_before = (b["endS"] - b["startS"]) * 0.45
            room_after = (nxt["endS"] - nxt["startS"]) * 0.45
            lo = max(mid - room_before, prev_window_end + 0.05)
            hi = mid + room_after
            if mid - d / 2 < lo or mid + d / 2 > hi:
                fit = 2 * min(mid - lo, hi - mid)
                if a.auto_fit and fit > 0.3:
                    warnings.append(f"{s['id']}: {typ} shortened from {d:.2f}s to {fit:.2f}s to fit the neighbouring scenes")
                    d = fit
                else:
                    die(f"{s['id']}: the {typ} transition ({d:.2f}s) does not fit between its neighbours (room {2 * min(mid - lo, hi - mid):.2f}s, previous transition ends {prev_window_end:.2f}s); shorten durationMs or the narration beats, or use --auto-fit")
            window = {"type": typ, "startS": round(mid - d / 2, 3), "endS": round(mid + d / 2, 3), "easing": tr.get("easing", "standard")}
            for key in ("anchorFrom", "anchorTo", "rationale", "downgradedFrom"):
                if tr.get(key):
                    window[key] = tr[key]
            if typ in CLAMPS and not dg and tr.get("anchorFrom") and tr.get("anchorTo") and k + 1 < len(order):
                # the operator locks the two anchors in position but can only match their drawn size within its clamp; beyond it the sizes drift apart mid-window
                nl = order[k + 1]["layouts"].get(layout) or order[k + 1]["layouts"]["landscape"]
                wa = (lay["placements"].get(tr["anchorFrom"]["entityId"]) or {}).get("w")
                wb = (nl["placements"].get(tr["anchorTo"]["entityId"]) or {}).get("w")
                if wa and wb:
                    lo, hi = CLAMPS[typ]
                    if not lo <= wb / wa <= hi:
                        warnings.append(f"{s['id']}>{order[k + 1]['id']}: the {typ} anchors differ in width by {max(wb / wa, wa / wb):.1f}x in the {layout} layout, but the operator can match at most {1 / lo:.0f}x; their sizes will not coincide mid-transition (use anchors of closer size, or another operator)")
            if dg:
                window["type"] = dg["type"]
                window["downgradedFrom"] = dg["downgradedFrom"]
                window["rationale"] = f"downgraded from {dg['downgradedFrom']} by the motion gate: {dg['check']} FAILED ({dg['finding']})"[:400]
                for key in ("anchorFrom", "anchorTo"):
                    window.pop(key, None)
                warnings.append(f"{s['id']}>{order[k + 1]['id']}: {dg['downgradedFrom']} replaced by {dg['type']} after {dg['check']} failed")
            ps["transitionOut"] = window
            prev_window_end = window["endS"]
        # a deliberate hold: only the genuinely still part of the scene is authorised
        if lay.get("hold"):
            still_from = max([e["enterS"] + e["enterMs"] / 1000 for e in ent] + [c["toS"] for c in cams] + [b["startS"]])
            still_to = (window["startS"] if window else b["endS"])
            if still_to - still_from >= 0.5:
                ps["hold"] = {"fromS": round(still_from, 3), "toS": round(still_to, 3), "reason": lay["hold"]["reason"]}
        plan_scenes.append(ps)

    # ── captions ──
    caps = caption_chunks([{k: v for k, v in w.items() if k != "own"} for w in words], max_words=max_words)
    plan = {
        "version": 1,
        "target": a.target,
        "layout": layout,
        "fps": fps,
        "width": W,
        "height": H,
        "durationS": round(dur, 3),
        "durationFrames": int(round(dur * fps)),
        "timingSource": timing_source,
        "pictureRegion": picture_region(tokens, layout),
        "audio": audio,
        "opening": sc.get("opening", {"fadeInMs": 0, "leadSilenceMs": 0}) if not is_short else {"fadeInMs": 0, "leadSilenceMs": 0},
        "ending": sc.get("ending", {"fadeOutMs": 0, "holdBlackMs": 0, "tailSilenceMs": 0}) if not is_short else {"fadeOutMs": 0, "holdBlackMs": 0, "tailSilenceMs": 0},
        "scenes": plan_scenes,
        "words": [{k: v for k, v in w.items() if k != "own"} for w in words],
        "captions": caps,
        "silences": silences,
        "warnings": warnings,
    }
    out = a.out or P("render", f"plan-{a.target}.json")
    write_json(out, plan)
    print(f"plan {a.target}: {len(plan_scenes)} scenes, {dur:.1f}s @ {fps} fps {W}x{H} ({layout}), {sum(1 for s in plan_scenes if s.get('transitionOut'))} transitions, {len(caps)} caption phrases, timing from {timing_source} -> {out}")
    for w in warnings:
        print("warn:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
