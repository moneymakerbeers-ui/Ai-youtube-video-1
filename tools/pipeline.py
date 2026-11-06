#!/usr/bin/env python3
"""pipeline.py - the deterministic production CLI: one command turns a project's scene data into the long video and every validated Short.

  python tools/pipeline.py run --project videos/<slug> [--stack auto|flite|file|elevenlabs] [--voice slt] [--targets long,S01]
                               [--size 1920x1080] [--fps N] [--workers 2] [--only STEP,STEP|qa|audio|video] [--force] [--no-qa] [--auto-downgrade]
  python tools/pipeline.py steps                      list the steps
  python tools/pipeline.py status --project P         what ran, what is stale

The long video (16:9) and each Short (9:16) are rendered from the SAME scenes.json: the long uses every scene's landscape layout, a Short
uses its scenes' explicit portrait layouts, its own opening/closing lines and its own assembled, re-aligned audio.
Steps (a finished step whose inputs are unchanged is skipped, so a re-run or `/make resume` continues instead of redoing):
  validate  visuals  voice  assemble  align  short:<id>  plan:<t>  lint:<t>  mix:<t>  render:<t>  captions:<t>  allow:<t>  qa:<t>  motion:<t>  report
Outputs: out/full-video.mp4, out/short-NN.mp4, out/captions.srt, out/short-NN.srt, qa/*.json, render/plan-*.json, render/trace-*.json, audio/master-*.wav.
Paid calls never happen here except through voice.py's ledger-gated ElevenLabs adapter. The default stack is `auto`: ElevenLabs only when a key is present AND the spend gate approved it, otherwise the free local voice (flite) with a FALLBACK note.
Exit: 0 all steps ok · 1 a QA gate FAILED · 2 bad input · 3 BLOCKED (a tool, key or approval is missing) · 4 a step failed · 5 the creative preview gate is not approved.
"""
import argparse, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from common import preview_gate, read_json, write_json  # noqa: E402

PY = sys.executable


def sha_files(paths, extra=""):
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(p.encode())
        if os.path.isfile(p):
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        else:
            h.update(b"<missing>")
    return h.hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


MAX_DOWNGRADE_ROUNDS = 2


class Pipeline:
    def __init__(self, a):
        self.a = a
        self.P = os.path.abspath(a.project)
        self.stamps_path = os.path.join(self.P, "render", "stamps.json")
        self.stamps = read_json(self.stamps_path) if os.path.exists(self.stamps_path) else {}
        self.results = []
        self.qa = {}

    def p(self, *x):
        return os.path.join(self.P, *x)

    GROUPS = {"qa": ("allow", "qa", "motion"), "audio": ("voice", "assemble", "align", "short"), "video": ("visuals", "plan", "lint", "mix", "render", "captions")}

    def selected(self, name):
        o = self.a.only
        if not o:
            return True
        want = {y for x in o for y in self.GROUPS.get(x, (x,))}
        return name in want or name.split(":")[0] in want

    def sh(self, name, cmd, cwd=REPO, env=None):
        os.makedirs(self.p("render", "logs"), exist_ok=True)
        log = self.p("render", "logs", name.replace(":", "_") + ".log")
        t0 = time.time()
        with open(log, "w") as f:
            f.write("$ " + " ".join(map(str, cmd)) + "\n")
            f.flush()
            r = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})})
        return r.returncode, log, time.time() - t0

    def step(self, name, inputs, outputs, cmd, extra="", accept=(0,), env=None):
        a = self.a
        if not self.selected(name):
            return None
        code = expand(CODE.get(name.split(":")[0], []))
        grp = name.split(":")[0]
        faults = "|".join(f"{k}={os.environ[k]}" for k, g in (("QA_FAULT", ("allow", "qa", "motion")), ("PAID_FAULT", ("voice",))) if os.environ.get(k) and grp in g)  # fault-injection runs never reuse (or leave) a clean cache entry
        key = sha_files(list(inputs) + [c for c in code if c not in inputs], extra + " ".join(map(str, cmd)) + json.dumps(env or {}, sort_keys=True) + faults)
        # A missing/corrupt/truncated output must never be trusted on resume merely
        # because its filename and input fingerprint still match an old stamp.
        old_stamp = self.stamps.get(name, {})
        saved_outputs = old_stamp.get("outputHashes", {})
        done = (bool(outputs) and old_stamp.get("key") == key
                and all(os.path.isfile(o) and saved_outputs.get(o) == file_sha256(o) for o in outputs))
        if done and not a.force:
            print(f"  skip   {name}  (inputs unchanged)")
            self.results.append({"step": name, "status": "skipped"})
            return 0
        rc, log, secs = self.sh(name, cmd, env=env)
        tail = "".join(open(log).readlines()[-12:]).rstrip()
        status = "ok" if rc in accept else ("blocked" if rc == 3 else "failed")
        self.results.append({"step": name, "status": status, "exit": rc, "seconds": round(secs, 1), "log": os.path.relpath(log, self.P)})
        if rc in accept:
            # Do not cache a successful exit that failed to produce its required artifacts.
            if any(not os.path.isfile(o) for o in outputs):
                print(f"  FAILED {name}: command returned {rc} but required output is missing", file=sys.stderr)
                return 4
            self.stamps[name] = {"key": key, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "seconds": round(secs, 1),
                                 "outputHashes": {o: file_sha256(o) for o in outputs}}
            write_json(self.stamps_path, self.stamps)
            last = [l for l in tail.splitlines() if l.strip()][-1:] or [""]
            print(f"  ok     {name}  ({secs:.0f}s)  {last[0][:110]}")
            return 0
        print(f"  {status.upper():6} {name}  (exit {rc})  log: {os.path.relpath(log, self.P)}\n" + "\n".join("         " + l for l in tail.splitlines()[-8:]))
        return rc


VISUAL_ONLY = ("layouts", "entities", "transition", "presentation", "visualIntensity", "look", "signature", "shortIds", "assetIds", "qaRisk", "claimIds", "intent", "retentionBeat", "timing")


def audio_digest(P):
    """What the audio steps depend on: the spoken words, their direction, pauses and Short lines. Layout, entities, transitions and
    other visual-only fields are removed, so editing a layout or a camera move never re-runs (or re-buys) the voice. Anything not
    listed in VISUAL_ONLY still counts, so a field that might matter can never be silently ignored."""
    sc = read_json(os.path.join(P, "scenes.json"))
    out = {"top": {k: v for k, v in sc.items() if k != "scenes"}, "scenes": [{k: v for k, v in s.items() if k not in VISUAL_ONLY} for s in sc["scenes"]]}
    sp = os.path.join(P, "shorts.json")
    if os.path.exists(sp):
        out["shorts"] = [{"id": x["id"], "sceneIds": x["sceneIds"], "delta": x.get("delta"), "status": x["status"], "openingLine": x.get("openingLine"), "closingLine": x.get("closingLine"), "targetDurationS": x.get("targetDurationS")} for x in read_json(sp)["shorts"]]
    return json.dumps(out, sort_keys=True, ensure_ascii=False)


# The code each step runs. A step's cache key includes these files, so upgrading a tool re-runs exactly the steps it affects (a stale
# plan or render can never be mistaken for a current one) while an unrelated tool change never re-runs, or re-buys, a paid voice step.
T = lambda *f: [os.path.join("tools", x) for x in f]  # noqa: E731
E = [os.path.join("engine", "src"), os.path.join("engine", "render.ts"), os.path.join("engine", "build.ts"), os.path.join("engine", "node-lib.ts"), os.path.join("schema", "video.schema.ts")]
CODE = {
    "validate": [os.path.join("schema", "validate.ts"), os.path.join("schema", "video.schema.ts")],
    "visuals": [os.path.join("engine", "visuals-manifest.ts"), os.path.join("engine", "src", "visuals")],
    "voice": T("voice.py", "voice_direction.py", "ledger.py", "common.py", "voice_flite.py", "audio_lib.py"),
    "assemble": T("assemble_audio.py", "audio_lib.py", "common.py"),
    "align": T("align.py", "audio_lib.py", "common.py"),
    "short": T("short_audio.py", "align.py", "audio_lib.py", "assemble_audio.py", "common.py"),
    "plan": T("make_plan.py", "plan_lib.py", "common.py") + [os.path.join("schema", "video.schema.ts")],
    "lint": T("make_allow.py", "plan_lib.py", "common.py"),
    "mix": T("mix.py", "audio_lib.py", "common.py"),
    "render": E,
    "captions": T("captions.py", "plan_lib.py", "common.py"),
    "allow": T("make_allow.py", "plan_lib.py", "common.py"),
    "qa": T("qa_media.py", "qa_core.py", "make_allow.py", "plan_lib.py", "common.py"),
    "motion": T("qa_motion.py", "qa_core.py", "common.py"),
}


def expand(paths):
    out = []
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(REPO, p)
        if os.path.isdir(full):
            for root, _, files in os.walk(full):
                out += [os.path.join(root, f) for f in sorted(files) if f.endswith((".ts", ".py", ".json"))]
        elif os.path.exists(full):
            out.append(full)
    return sorted(out)


def project_asset_files(project, manifest):
    """Find local assets for cache invalidation; never use paths outside the project."""
    data = read_json(manifest)
    found = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("file", "path", "src", "url", "pattern") and isinstance(v, str):
                    rel = v.split("{", 1)[0]
                    if rel and not rel.startswith(("http://", "https://", "data:")):
                        path = os.path.abspath(os.path.join(project, rel))
                        if os.path.commonpath([os.path.abspath(project), path]) == os.path.abspath(project) and os.path.isfile(path):
                            found.append(path)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(data)
    # Also include local files under assets/ even when a manifest's schema has a
    # different field name. This prevents a stale render after a retouched PNG.
    ad = os.path.join(project, "assets")
    if os.path.isdir(ad):
        found += [os.path.join(r, f) for r, _, fs in os.walk(ad) for f in fs if not f.startswith(".")]
    return sorted(set(found))


def targets_for(P, spec):
    shorts = []
    sp = os.path.join(P, "shorts.json")
    if os.path.exists(sp):
        shorts = [s["id"] for s in read_json(sp)["shorts"] if s["status"] == "validated"]
    if spec:
        want = spec.split(",")
        unknown = [t for t in want if t != "long" and t not in shorts]
        if unknown:
            print(f"unknown or non-validated targets: {unknown} (validated Shorts: {shorts})", file=sys.stderr)
            sys.exit(2)
        return want
    return ["long"] + shorts


def out_name(t):
    return "out/full-video.mp4" if t == "long" else f"out/short-{t[1:].zfill(2)}.mp4"


def cap_name(t):
    return "out/captions.srt" if t == "long" else f"out/short-{t[1:].zfill(2)}.srt"


def run(a):
    pl = Pipeline(a)
    P = pl.P
    for need in ("scenes.json", "config.json", "facts.json"):
        if not os.path.exists(pl.p(need)):
            print(f"{P}: {need} is missing (see docs/PROJECT-LAYOUT.md)", file=sys.stderr)
            return 2
    ok_gate, why_gate = preview_gate(P)
    if not ok_gate:
        print(f"PREVIEW GATE: {why_gate}", file=sys.stderr)
        return 5
    targets = targets_for(P, a.targets)
    shorts = [t for t in targets if t != "long"]
    size = ["--size", a.size] if a.size else []
    fps = ["--fps", str(a.fps)] if a.fps else []
    if not a.fps:
        try:
            cfg_fps = json.load(open(pl.p("config.json"))).get("fps")
        except Exception:  # noqa: BLE001
            cfg_fps = None
        if cfg_fps in (30, 60):  # "auto" means 30; 60 only when the creator asked for it
            fps = ["--fps", str(cfg_fps)]
    stack, notes = a.stack, []
    if stack == "auto":
        # the paid voice only when a key exists AND the creator approved it at the spend gate; otherwise the documented free fallback
        sys.path.insert(0, HERE)
        from ledger import Ledger
        svc = Ledger(P).service("elevenlabs")
        from voice_direction import resolve_elevenlabs
        why = "no ELEVENLABS_API_KEY" if not os.environ.get("ELEVENLABS_API_KEY") else ("not approved at the spend gate" if not (svc and svc.get("approved")) else ("no voice id (set config.json voice.elevenlabs.voiceId, ELEVENLABS_VOICE_ID or --voice-id)" if not resolve_elevenlabs(P, a.voice_id)[0] else None))
        # An approved professional voice must not quietly become a robotic voice
        # because its voice ID was omitted. Require the project to select a voice.
        if (os.environ.get("ELEVENLABS_API_KEY") and svc and svc.get("approved") and why):
            print("BLOCKED: ElevenLabs is approved, but " + why + ". Choose a suitable voice from the voice library and save its voiceId in config.json before rendering. No fallback has been substituted.", file=sys.stderr)
            return 3
        stack = "elevenlabs" if why is None else "flite"
        if why:
            notes.append(f"voice: ElevenLabs unavailable ({why}); FALLBACK to the free local voice flite (robotic, for drafts and tests)")
            print("  " + notes[-1])
    print(f"project {P}\ntargets {', '.join(targets)} · voice stack {stack} · {a.size or 'plan size'}")
    jobs = []

    def go(*args, fail_code=4, **kw):
        rc = pl.step(*args, **kw)
        if rc:  # None = not selected, 0 = ok/skipped
            raise SystemExit(rc if rc == 3 else fail_code)

    try:
        go("validate", [pl.p(f) for f in ("scenes.json", "config.json", "facts.json", "shorts.json", "style-tokens.json", "assets/manifest.json") if os.path.exists(pl.p(f))], [], ["npx", "tsx", "schema/validate.ts", "project", P])
        vis_src = [os.path.join(REPO, "engine", "src", "visuals", f) for f in ("builtin.ts", "types.ts")] + [os.path.join(REPO, "engine", "visuals-manifest.ts")]
        vdir = pl.p("visuals")
        vis_src += [os.path.join(vdir, f) for f in sorted(os.listdir(vdir))] if os.path.isdir(vdir) else []
        vman = pl.p("render", "visuals-manifest.json")
        go("visuals", vis_src, [vman], ["npx", "tsx", "engine/visuals-manifest.ts", "--project", P, "--out", vman])
        dig = audio_digest(P)
        # the DTW aligner compares the narration with a synthesised reference; when the narration is flite speech the reference must be the
        # SAME flite voice (a different voice moved word boundaries by up to 0.5 s in connected speech; the same voice, by ~0.05 s)
        ref_env = {"ALIGN_REF_VOICE": a.voice} if stack == "flite" else {}
        go("voice", [], [pl.p("audio", "takes.json"), pl.p("audio", "voice.json")], [PY, "tools/voice.py", "--project", P, "--stack", stack, "--voice", a.voice] + (["--voice-id", a.voice_id] if a.voice_id else []), extra=f"{stack}|{a.voice}|{a.voice_id}|{dig}|{open(pl.p('config.json')).read() if os.path.exists(pl.p('config.json')) else ''}")
        takes_dir = pl.p("audio", "takes")
        take_files = [pl.p("audio", "takes", f) for f in sorted(os.listdir(takes_dir))] if os.path.isdir(takes_dir) else []
        go("assemble", [pl.p("audio", "takes.json")] + take_files, [pl.p("audio", "narration.wav"), pl.p("audio", "assembly.json")],
           [PY, "tools/assemble_audio.py", "--scenes", pl.p("scenes.json"), "--takes", pl.p("audio", "takes.json"), "--out", pl.p("audio", "narration.wav"), "--assembly", pl.p("audio", "assembly.json"), "--project", P], extra=dig)
        go("align", [pl.p("audio", "narration.wav"), pl.p("audio", "assembly.json")], [pl.p("audio", "alignment.json")],
           [PY, "tools/align.py", "--audio", pl.p("audio", "narration.wav"), "--assembly", pl.p("audio", "assembly.json"), "--scenes", pl.p("scenes.json"), "--script", pl.p("audio", "spoken_script.txt"), "--out", pl.p("audio", "alignment.json"), "--engine", "dtw" if stack == "flite" else "auto", "--project", P], extra=dig, env=ref_env)
        for t in shorts:
            lines = [pl.p("audio", "shorts", t, f) for f in ("opening.wav", "closing.wav") if os.path.exists(pl.p("audio", "shorts", t, f))]
            go(f"short:{t}", [pl.p("audio", "alignment.json")] + lines, [pl.p("audio", "shorts", t, "alignment.json")],
               [PY, "tools/short_audio.py", "--project", P, "--short", t, "--engine", "dtw" if stack == "flite" else "auto"], extra=dig, env=ref_env)
        def build(t):
            plan_in = [pl.p("scenes.json"), pl.p("style-tokens.json"), pl.p("config.json"), vman, pl.p("render", "downgrades.json"), pl.p("audio", "alignment.json") if t == "long" else pl.p("audio", "shorts", t, "alignment.json")]
            go(f"plan:{t}", plan_in, [pl.p("render", f"plan-{t}.json")], [PY, "tools/make_plan.py", "--project", P, "--target", t, "--auto-fit", "--visuals", vman] + size + fps)
            if not a.no_lint:
                # fail fast, before an expensive render: unplanned stillness the QA would reject anyway
                thr_l = os.path.join(REPO, "library", "thresholds.json")
                go(f"lint:{t}", [pl.p("render", f"plan-{t}.json"), pl.p("style-tokens.json"), thr_l, os.path.join(HERE, "make_allow.py")], [],
                   [PY, "tools/make_allow.py", "--plan", pl.p("render", f"plan-{t}.json"), "--tokens", pl.p("style-tokens.json"), "--thresholds", thr_l, "--check"], fail_code=1)
            # optional per-target sound bed (written for this target's own timeline, each with a .license.json): a music bed (ducked) and an effects track
            bed_in, bed_args = [], []
            for kind, flag in (("music", "--music"), ("fx", "--fx")):
                f = pl.p("audio", "bed", f"{kind}-{t}.wav")
                if os.path.exists(f):
                    bed_in += [f, f + ".license.json"]
                    bed_args += [flag, os.path.join("audio", "bed", f"{kind}-{t}.wav")]
            if bed_args:
                bed_args += ["--music-db", "0"]  # the bed is written at its intended level; mix.py only ducks it under speech
            go(f"mix:{t}", [pl.p("render", f"plan-{t}.json")] + bed_in, [pl.p("audio", f"master-{t}.wav")], [PY, "tools/mix.py", "--project", P, "--target", t] + bed_args)
            # Render validity depends on the contents of image assets and custom
            # visual source files, not just on their filenames in scenes.json.
            manifest_path = pl.p("assets", "manifest.json")
            asset_inputs = [manifest_path] if os.path.isfile(manifest_path) else []
            if asset_inputs:
                asset_inputs += project_asset_files(P, manifest_path)
            custom_dir = pl.p("visuals")
            if os.path.isdir(custom_dir):
                asset_inputs += [os.path.join(r, f) for r, _, fs in os.walk(custom_dir) for f in fs if f.endswith((".ts", ".tsx", ".js", ".json"))]
            go(f"render:{t}", [pl.p("render", f"plan-{t}.json"), pl.p("audio", f"master-{t}.wav"), pl.p("style-tokens.json"), pl.p("scenes.json")] + asset_inputs + [os.path.join(REPO, "engine", f) for f in ("render.ts", "build.ts")] + expand([os.path.join(REPO, "engine", "src")]),
               [pl.p(out_name(t)), pl.p("render", f"trace-{t}.json")], ["npx", "tsx", "engine/render.ts", "--project", P, "--target", t, "--workers", str(a.workers)])
            go(f"captions:{t}", [pl.p("render", f"plan-{t}.json")], [pl.p(cap_name(t))], [PY, "tools/captions.py", "--plan", pl.p("render", f"plan-{t}.json"), "--out", pl.p(cap_name(t))])

        for t in targets:
            build(t)
        if not a.no_qa:
            for t in targets:
                qa_target(pl, t)
                # a complex transition the motion gate rejected falls back to a dissolve (recorded in render/downgrades.json), then the SAME gates judge the new render
                for rnd in range(1, MAX_DOWNGRADE_ROUNDS + 1):
                    if not (a.auto_downgrade and pl.qa.get(t) == "FAILED"):
                        break
                    rc = subprocess.run([PY, os.path.join(HERE, "downgrade.py"), "--project", P, "--target", t, "--motion", pl.p("qa", f"motion-{t}.json")], cwd=REPO).returncode
                    if rc != 0:
                        break  # nothing a safer operator can fix: the verdict stays FAILED
                    notes.append(f"{t}: transition downgraded after the motion gate failed (round {rnd}); see render/downgrades.json")
                    build(t)
                    qa_target(pl, t)
    except SystemExit as e:
        write_json(pl.p("render", "pipeline-last.json"), {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "targets": targets, "stack": stack, "notes": notes, "results": pl.results, "qa": pl.qa, "stoppedWith": int(e.code or 0)})
        write_report(P)
        return int(e.code or 0)
    write_json(pl.p("render", "pipeline-last.json"), {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "targets": targets, "stack": stack, "notes": notes, "results": pl.results, "qa": pl.qa})
    write_report(P)
    print("\nQA verdicts: " + ", ".join(f"{t}: {v}" for t, v in pl.qa.items()) if pl.qa else "\n(QA skipped)")
    if any(v == "FAILED" for v in pl.qa.values()):
        return 1
    if any(v == "BLOCKED" for v in pl.qa.values()):
        return 3
    return 0


def write_report(P):
    """review/production-report.md from the run's own files (also after a stopped or failed run: the report then says what stopped it)."""
    r = subprocess.run([PY, os.path.join(HERE, "report.py"), "--project", P], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        print(f"  (the production report could not be written: {(r.stderr or r.stdout).strip()[-160:]})")


def qa_target(pl, t):
    P = pl.P
    plan, trace = pl.p("render", f"plan-{t}.json"), pl.p("render", f"trace-{t}.json")
    video = pl.p(out_name(t))
    tokens = pl.p("style-tokens.json")
    thr = os.path.join(REPO, "library", "thresholds.json")
    allow = pl.p("qa", f"allow-{t}.json")
    rc = pl.step(f"allow:{t}", [plan, tokens], [allow], [PY, "tools/make_allow.py", "--plan", plan, "--tokens", tokens, "--thresholds", thr, "--out", allow])
    if rc:
        raise SystemExit(4)
    if rc is None:
        return
    qa_in = [video, plan, allow, trace, pl.p("audio", f"master-{t}.wav"), thr] + [os.path.join(HERE, f) for f in ("qa_media.py", "qa_core.py", "make_allow.py")]
    # QA verdicts are results, not artefacts to cache: exit 1 (FAILED) and 3 (BLOCKED) are valid outcomes of the step
    m = pl.step(f"qa:{t}", qa_in, [pl.p("qa", f"{t}.json")], [PY, "tools/qa_media.py", video, "--plan", plan, "--allow", allow, "--tokens", tokens, "--trace", trace, "--master", pl.p("audio", f"master-{t}.wav"), "--thresholds", thr, "--out", pl.p("qa", f"{t}.json"), "--sheets", pl.p("qa", "sheets", t)], accept=(0, 1, 3))
    nar = pl.p(read_json(plan)["audio"]["file"]) if os.path.exists(plan) and (read_json(plan).get("audio") or {}).get("file") else None
    mo = pl.step(f"motion:{t}", qa_in + [os.path.join(HERE, "qa_motion.py")] + ([nar] if nar else []), [pl.p("qa", f"motion-{t}.json")], [PY, "tools/qa_motion.py", video, "--plan", plan, "--trace", trace, "--thresholds", thr, "--out", pl.p("qa", f"motion-{t}.json"), "--previews", pl.p("render", "previews", t)] + (["--narration", nar] if nar else []), accept=(0, 1, 3))
    if m or mo:
        raise SystemExit(4)
    if m is None or mo is None:  # a partial run (--only) that skipped a QA step: nothing to report for this target
        return
    verdicts = [read_json(pl.p("qa", f"{t}.json"))["overall"], read_json(pl.p("qa", f"motion-{t}.json"))["overall"]]
    pl.qa[t] = "FAILED" if "FAILED" in verdicts else "BLOCKED" if "BLOCKED" in verdicts else "PASSED"
    print(f"  QA {t}: media {verdicts[0]}, motion {verdicts[1]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--project", required=True)
    r.add_argument("--stack", default="auto", choices=["auto", "flite", "file", "elevenlabs"])
    r.add_argument("--voice", default="slt")
    r.add_argument("--voice-id")
    r.add_argument("--targets")
    r.add_argument("--size")
    r.add_argument("--fps", type=int)
    r.add_argument("--workers", type=int, default=2)
    r.add_argument("--only", type=lambda s: s.split(","), help="comma-separated step names to run (others are skipped)")
    r.add_argument("--force", action="store_true")
    r.add_argument("--no-qa", action="store_true")
    r.add_argument("--no-lint", action="store_true", help="render even when the plan predicts unplanned stillness (previews only)")
    r.add_argument("--auto-downgrade", action="store_true")
    sub.add_parser("steps")
    s = sub.add_parser("status")
    s.add_argument("--project", required=True)
    a = ap.parse_args()
    if a.cmd == "steps":
        print("validate visuals voice assemble align short:<id> plan:<t> lint:<t> mix:<t> render:<t> captions:<t> allow:<t> qa:<t> motion:<t> report\ngroups for --only: audio = voice assemble align short · video = visuals plan lint mix render captions · qa = allow qa motion")
        return 0
    if a.cmd == "status":
        st = os.path.join(a.project, "render", "stamps.json")
        for k, v in (read_json(st) if os.path.exists(st) else {}).items():
            print(f"{k:16} {v['at']}  {v['seconds']}s")
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
