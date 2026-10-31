#!/usr/bin/env python3
"""preview.py - the creative preview gate: what the creator sees and approves BEFORE the full render and before any paid voice or generation is spent.

  python tools/preview.py make    --project P [--size 640x360] [--hero ID] [--technical ID] [--transition FROM>TO]
                                  [--voice-stack flite|elevenlabs] [--voice slt] [--voice-id ID]
  python tools/preview.py approve --project P [--note TEXT]
  python tools/preview.py status  --project P

`make` writes review/preview/ :
  hero-landscape.png  hero-portrait.png          the scene that carries the most visual weight, in 16:9 and 9:16
  technical-landscape.png  technical-portrait.png  the scene with the most data-bearing graphics (the legibility test)
  transition-<from>-<to>-landscape.mp4 / -portrait.mp4   the first complex transition (optional: only when the project has one)
  voice-sample.wav                                the first lines in the chosen voice (free draft voice, or a spend-gated sample)
  contact.png  preview.md  preview.json
Timing in these previews is ESTIMATED from the text (there is no narration yet); assets that are not generated yet are drawn as labelled placeholders.
Nothing here is a QA verdict. `approve` records the creator's yes in state.json together with the creative fingerprint (look, voice direction,
scene structure); pipeline.py refuses to run for a project with config.previewGate = "required" until that approval matches the current fingerprint.
Exit: 0 ok · 1 nothing to preview / approval does not match / render failed · 2 bad input · 3 BLOCKED (tool missing)
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import creative_fingerprint, preview_gate, read_json, write_json  # noqa: E402
from ledger import Ledger  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
DATA_LIKE = ("bars", "counter", "grid", "flow", "aspect_frame", "wave", "arrow")


def sh(cmd, log):
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "w") as f:
        f.write("$ " + " ".join(map(str, cmd)) + "\n")
        f.flush()
        r = subprocess.run([str(c) for c in cmd], cwd=REPO, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode, "".join(open(log).readlines()[-6:]).strip()


def comps(scene):
    return [(e.get("visual") or {}).get("component") for e in scene.get("entities", []) if (e.get("visual") or {}).get("component")]


def choose(scenes, need_portrait, a):
    """hero, technical, transition pair. Overrides win; otherwise the scene with the highest visual intensity (then most entities / a camera move)
    and the scene with the most data-bearing graphics."""
    pool = [s for s in scenes if (not need_portrait) or (s.get("layouts") or {}).get("portrait")]
    if not pool:
        return None, None, None
    by = {s["id"]: s for s in pool}
    weight = lambda s: (s.get("visualIntensity", 1), len(s.get("entities", [])) + 2 * len(((s.get("layouts") or {}).get("portrait" if need_portrait else "landscape") or {}).get("camera", [])))  # noqa: E731
    hero = by.get(a.hero) or max(pool, key=weight)
    rest = [s for s in pool if s["id"] != hero["id"]] or [hero]
    data = lambda s: sum(c in DATA_LIKE or c not in ("text", "caption") for c in comps(s))  # noqa: E731
    technical = by.get(a.technical) or max(rest, key=lambda s: (data(s), len(s.get("entities", []))))
    ids = {s["id"]: i for i, s in enumerate(scenes)}
    pair = None
    if a.transition:
        f, _, t = a.transition.partition(">")
        pair = (by.get(f), by.get(t)) if f in by and t in by else None
    else:
        for i in range(len(scenes) - 1):
            s, n = scenes[i], scenes[i + 1]
            if (s.get("transition") or {}).get("type", "cut") not in ("cut", "dissolve") and s["id"] in by and n["id"] in by:
                pair = (s, n)
                break
    return hero, technical, pair


def make(a):
    P = os.path.abspath(a.project)
    out_dir = os.path.join(P, "review", "preview")
    os.makedirs(out_dir, exist_ok=True)
    logd = os.path.join(P, "render", "preview", "logs")
    rc, tail = sh(["npx", "tsx", "schema/validate.ts", "project", P], os.path.join(logd, "validate.log"))
    if rc:
        print(f"the project does not validate yet, so there is nothing trustworthy to preview:\n{tail}", file=sys.stderr)
        return 2
    scenes = read_json(os.path.join(P, "scenes.json"))["scenes"]
    size = a.size or "640x360"
    W, H = map(int, size.lower().split("x"))
    sizes = {"landscape": f"{max(W, H)}x{min(W, H)}", "portrait": f"{min(W, H)}x{max(W, H)}"}
    notes, files, picks = [], {}, {}
    fps = 30
    for layout in ("landscape", "portrait"):
        suffix = "" if layout == "landscape" else "-portrait"
        hero, tech, pair = choose(scenes, layout == "portrait", a)
        if not hero:
            notes.append(f"{layout}: no scene has a {layout} layout, so there is no {layout} preview (Shorts cannot be made from this project until a scene has one)")
            continue
        if layout == "portrait" and hero["id"] != picks.get("landscape", {}).get("hero"):
            notes.append(f"portrait: the hero is {hero['id']} (the landscape hero has no portrait layout)")
        picks[layout] = {"hero": hero["id"], "technical": tech["id"], "transition": f"{pair[0]['id']}>{pair[1]['id']}" if pair else None}
        ids = [hero["id"]] + ([tech["id"]] if tech["id"] != hero["id"] else [])
        # stills
        target = f"preview-stills{suffix}"
        plan_file = os.path.join(P, "render", "preview", f"plan-{target}.json")
        rc, tail = sh([PY, "tools/make_plan.py", "--project", P, "--target", target, "--scenes", ",".join(ids), "--size", sizes[layout], "--auto-fit", "--out", plan_file], os.path.join(logd, f"plan-{target}.log"))
        if rc:
            print(f"{layout} plan failed:\n{tail}", file=sys.stderr)
            return 1
        plan = read_json(plan_file)
        fps = plan["fps"]
        times = {}
        for sc in plan["scenes"]:
            times[sc["id"]] = round(sc["startS"] + 0.85 * (sc["endS"] - sc["startS"]), 3)
        frames = {sid: min(int(round(t * fps)), plan["durationFrames"] - 1) for sid, t in times.items()}
        fdir = os.path.join(P, "render", "preview", "frames")
        rc, tail = sh(["npx", "tsx", "engine/render.ts", "--project", P, "--target", target, "--plan", plan_file, "--dump-frames", ",".join(map(str, frames.values())), "--dump-dir", fdir, "--audio", "none", "--allow-placeholders"], os.path.join(logd, f"stills-{target}.log"))
        if rc:
            print(f"{layout} stills failed (render exit {rc}):\n{tail}", file=sys.stderr)
            return 3 if rc == 4 else 1
        for role, sid in (("hero", hero["id"]), ("technical", tech["id"])):
            src = os.path.join(fdir, f"{target}-f{frames[sid]:06d}.png")
            dst = os.path.join(out_dir, f"{role}-{layout}.png")
            if os.path.exists(src):
                os.replace(src, dst) if role == "hero" or tech["id"] != hero["id"] else open(dst, "wb").write(open(src, "rb").read())
                files[f"{role}-{layout}"] = os.path.relpath(dst, P)
        # the optional complex transition
        if pair:
            target = f"preview-tr{suffix}"
            plan_file = os.path.join(P, "render", "preview", f"plan-{target}.json")
            rc, tail = sh([PY, "tools/make_plan.py", "--project", P, "--target", target, "--scenes", f"{pair[0]['id']},{pair[1]['id']}", "--size", sizes[layout], "--auto-fit", "--out", plan_file], os.path.join(logd, f"plan-{target}.log"))
            tw = (read_json(plan_file)["scenes"][0].get("transitionOut") if rc == 0 else None)
            if tw:
                plan = read_json(plan_file)
                f0, f1 = max(int(round((tw["startS"] - 0.6) * fps)), 0), min(int(round((tw["endS"] + 0.6) * fps)), plan["durationFrames"])
                dst = os.path.join(out_dir, f"transition-{pair[0]['id']}-{pair[1]['id']}-{layout}.mp4")
                rc, tail = sh(["npx", "tsx", "engine/render.ts", "--project", P, "--target", target, "--plan", plan_file, "--range", f"{f0}:{f1}", "--out", dst, "--audio", "none", "--allow-placeholders"], os.path.join(logd, f"clip-{target}.log"))
                if rc == 0 and os.path.exists(dst):
                    files[f"transition-{layout}"] = os.path.relpath(dst, P)
                else:
                    notes.append(f"{layout}: the transition clip could not be rendered (render exit {rc}): {tail[-160:]}")
            else:
                notes.append(f"{layout}: the transition between {pair[0]['id']} and {pair[1]['id']} did not fit its neighbours in the preview plan (no clip)")
    if not any(k.startswith("hero") for k in files):
        print("no preview could be rendered:\n  " + "\n  ".join(notes), file=sys.stderr)
        return 1
    # voice sample
    voice = {"status": "NOT MADE"}
    first = scenes[0]["narration"].strip()
    sample_text = first if len(first) <= 160 else first[:160].rsplit(" ", 1)[0]
    cmd = [PY, "tools/voice.py", "--project", P, "--stack", a.voice_stack, "--voice", a.voice, "--sample", sample_text, "--sample-out", "review/preview/voice-sample.wav"] + (["--voice-id", a.voice_id] if a.voice_id else [])
    rc, tail = sh(cmd, os.path.join(logd, "voice-sample.log"))
    if rc == 0:
        voice = {"status": "MADE", "stack": a.voice_stack, "voice": a.voice_id or a.voice, "chars": len(sample_text), "file": "review/preview/voice-sample.wav",
                 "meaning": "the free local draft voice (robotic): NOT the voice of a polished video; approve it only if the free path is what you want" if a.voice_stack == "flite" else "the production voice"}
        files["voice-sample"] = "review/preview/voice-sample.wav"
    else:
        voice = {"status": {3: "BLOCKED", 4: "REFUSED"}.get(rc, "FAILED"), "stack": a.voice_stack, "reason": tail[-300:]}
        notes.append(f"voice sample not made ({voice['status']}): {tail[-200:]}")
    # contact sheet
    try:
        from PIL import Image, ImageDraw
        tiles = [(k, os.path.join(P, v)) for k, v in files.items() if v.endswith(".png")]
        if tiles:
            th = 360
            ims = []
            for k, f in sorted(tiles):
                im = Image.open(f).convert("RGB")
                im = im.resize((int(im.width * th / im.height), th))
                ImageDraw.Draw(im).text((8, 6), k, fill=(255, 255, 255))
                ims.append(im)
            sheet = Image.new("RGB", (sum(i.width for i in ims) + 8 * (len(ims) + 1), th + 16), (24, 24, 28))
            x = 8
            for im in ims:
                sheet.paste(im, (x, 8))
                x += im.width + 8
            sheet.save(os.path.join(out_dir, "contact.png"))
            files["contact"] = "review/preview/contact.png"
    except Exception as e:  # noqa: BLE001
        notes.append(f"contact sheet not made: {e}")
    doc = {"createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "fingerprint": creative_fingerprint(P), "size": sizes, "timing": "estimated from the text; no narration exists yet",
           "selection": picks, "files": files, "voiceSample": voice, "notes": notes}
    write_json(os.path.join(out_dir, "preview.json"), doc)
    md = ["# Creative preview", "", f"Made {doc['createdAt']} at {size}. Timing is estimated (no narration yet) and assets that do not exist yet are labelled placeholders.", ""]
    for k, v in files.items():
        md.append(f"- **{k}**: `{v}`")
    md += ["", f"Voice sample: {voice['status']}" + (f" - {voice.get('meaning', '')}" if voice["status"] == "MADE" else f" - {voice.get('reason', '')}"), "", "Approve when the hero reads at a glance in both shapes, the technical shot is legible on a phone, the transition (if any) feels motivated, and the voice is the one you want. Then: `python tools/preview.py approve --project <dir>`."]
    if notes:
        md += ["", "Notes:"] + [f"- {n}" for n in notes]
    open(os.path.join(out_dir, "preview.md"), "w").write("\n".join(md) + "\n")
    print("creative preview -> review/preview/ (" + ", ".join(sorted(files)) + ")")
    for n in notes:
        print("  note: " + n)
    return 0


def approve(a):
    P = os.path.abspath(a.project)
    pj = os.path.join(P, "review", "preview", "preview.json")
    if not os.path.exists(pj):
        print("there is no preview to approve: run `python tools/preview.py make --project <dir>` and show review/preview/ to the creator first", file=sys.stderr)
        return 1
    cur = creative_fingerprint(P)
    if read_json(pj)["fingerprint"] != cur:
        print("the look, voice direction or scene structure changed after this preview was made: make a new preview before asking for approval", file=sys.stderr)
        return 1
    L = Ledger(P)
    st = L.state()
    st["previewGate"] = {"approved": True, "fingerprint": cur, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": a.note or ""}
    L.save_state(st)
    print("creative preview approved (recorded in state.json)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--project", required=True)
    m.add_argument("--size")
    m.add_argument("--hero")
    m.add_argument("--technical")
    m.add_argument("--transition")
    m.add_argument("--voice-stack", default="flite", choices=["flite", "elevenlabs"])
    m.add_argument("--voice", default="slt")
    m.add_argument("--voice-id")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("--project", required=True)
    ap_.add_argument("--note")
    s = sub.add_parser("status")
    s.add_argument("--project", required=True)
    a = ap.parse_args()
    if a.cmd == "make":
        return make(a)
    if a.cmd == "approve":
        return approve(a)
    ok, why = preview_gate(os.path.abspath(a.project))
    print(("APPROVED: " if ok else "NOT APPROVED: ") + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
