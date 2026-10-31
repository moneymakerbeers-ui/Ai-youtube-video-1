#!/usr/bin/env python3
"""voice.py - stage 03 narration: plan the takes, synthesise them with the chosen voice stack, write audio/takes.json.

Stacks (the identity of the narrator is fixed per video; delivery varies per scene through scenes.json voice{}):
  flite        C  FREE local TTS (ffmpeg libflite). Robotic, no emotion; exists so everything downstream can run with no account. TESTED.
  file         D  takes recorded or downloaded elsewhere (a human, Higgsfield voice, any studio): put audio/takes/<takeId>.wav in the project
                  (see audio/take-plan.json for the exact text of each take) and run this stack to validate and register them. TESTED.
  elevenlabs   A  ElevenLabs text-to-speech through tools/ledger.py (spend-gated, idempotent, resumable). Mock-server TESTED; live UNTESTED.
Higgsfield voice (B) is called by Claude through the Higgsfield MCP tools, one call per take in audio/take-plan.json, each wrapped in
`ledger.py intent/submitted/done`; the audio is then registered with `--stack file`. Whether the sandbox can download that result is
environment-dependent (see docs/STATUS.md).

usage:
  python tools/voice.py --project P --plan-only                       write audio/take-plan.json (takes, texts with TTS-only respellings, char counts) and stop
  python tools/voice.py --project P --stack flite [--voice slt]
  python tools/voice.py --project P --stack file
  python tools/voice.py --project P --stack elevenlabs --voice-id ID [--model eleven_multilingual_v2] [--base-url https://api.elevenlabs.io]
Also synthesises each validated Short's own opening/closing line (shorts.json delta) into audio/shorts/<id>/opening.wav|closing.wav in the SAME voice.
Exit: 0 ok · 2 bad input · 3 BLOCKED (tool/key missing) · 4 refused by the spend gate · 5/6 resume needs a provider lookup (see ledger.py).
"""
import argparse, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice_flite  # noqa: E402
import voice_direction  # noqa: E402
from common import duration_s, read_json, run, sha256_file, sha256_text, write_json  # noqa: E402
from ledger import Ledger, PaidCall, Refused  # noqa: E402

MAX_CHARS = {"flite": 600, "elevenlabs": 1200, "file": 1200}


def tts_text(narration, pronunciation):
    """The words sent to a synthesiser: respellings applied, everything else untouched. Captions and alignment use the plain narration."""
    out = narration
    for p in pronunciation or []:
        out = re.sub(r"(?<![\w'])" + re.escape(p["word"]) + r"(?![\w'])", p["say"], out)
    return out


def plan_takes(scenes, stack="flite"):
    """Group consecutive scenes into takes. A take never spans a declared pause or a change of delivery (pace/intensity/emotion)."""
    takes, cur = [], None
    for k, s in enumerate(scenes):
        v = s["voice"]
        prev = scenes[k - 1] if k else None
        brk = cur is None
        if prev is not None and not brk:
            if prev["voice"].get("pauseAfterMs", 0) + v.get("pauseBeforeMs", 0) > 0:
                brk = True
            pv = prev["voice"]
            if (pv.get("pace", "steady"), pv.get("intensity", 0), pv.get("emotion", "neutral-clear")) != (v.get("pace", "steady"), v.get("intensity", 0), v.get("emotion", "neutral-clear")):
                brk = True
            if len(cur["text"]) + len(s["narration"]) + 1 > MAX_CHARS.get(stack, 1200):
                brk = True
        if brk:
            cur = {"takeId": f"t{len(takes) + 1:02d}", "sceneIds": [], "text": "", "pace": v.get("pace", "steady"), "intensity": v.get("intensity", 0), "emotion": v.get("emotion", "neutral-clear")}
            takes.append(cur)
        cur["sceneIds"].append(s["id"])
        t = tts_text(s["narration"].strip(), v.get("pronunciation"))
        cur["text"] = (cur["text"] + " " + t).strip()
    for t in takes:
        t["chars"] = len(t["text"])
        t["file"] = f"audio/takes/{t['takeId']}.wav"
    return takes


def short_lines(project):
    p = os.path.join(project, "shorts.json")
    out = []
    if os.path.exists(p):
        for sh in read_json(p)["shorts"]:
            if sh["status"] == "validated":
                for kind in ("opening", "closing"):
                    t = sh.get("delta", {}).get(kind + "Line")
                    if t:
                        out.append({"short": sh["id"], "kind": kind, "text": t.strip(), "file": f"audio/shorts/{sh['id']}/{kind}.wav", "chars": len(t.strip())})
    return out


# ───────────────────────────── ElevenLabs (spend-gated) ─────────────────────────────
class ElevenLabs:
    def __init__(self, key, base="https://api.elevenlabs.io", model="eleven_multilingual_v2", settings=None):
        self.key, self.base, self.model = key, base.rstrip("/"), model
        self.settings = settings or {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}

    def _req(self, method, path, body=None, timeout=120):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), method=method, headers={"xi-api-key": self.key, "Content-Type": "application/json", "Accept": "*/*"})
        return urllib.request.urlopen(req, timeout=timeout)

    def tts(self, voice_id, text, settings=None):
        r = self._req("POST", f"/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128", {"text": text, "model_id": self.model, "voice_settings": settings or self.settings})
        return r.read(), r.headers.get("request-id") or r.headers.get("x-request-id") or "no-request-id"

    def find_in_history(self, voice_id, text, since_unix):
        r = self._req("GET", "/v1/history?page_size=100")
        for it in json.loads(r.read()).get("history", []):
            if it.get("voice_id") == voice_id and (it.get("text") or "").strip() == text.strip() and int(it.get("date_unix", 0)) >= since_unix - 5:
                return it["history_item_id"]
        return None

    def history_audio(self, item_id):
        return self._req("GET", f"/v1/history/{item_id}/audio").read()


def to_wav(src, dst, sr=24000):
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", src, "-ac", "1", "-ar", str(sr), dst])
    if duration_s(dst) < 0.15:
        raise RuntimeError(f"empty audio from {src}")


def synth_elevenlabs(project, items, voice_id, model, base, base_settings=None, sensitivity="normal"):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("BLOCKED: ELEVENLABS_API_KEY is not set (put it in .env or the environment; nothing was requested or charged)", file=sys.stderr)
        return 3
    el = ElevenLabs(key, base, model)
    # Count the actual payload, including v3 delivery tags. A spend gate must
    # never under-reserve simply because TTS directives were added later.
    prepared = []
    for i in items:
        syn = voice_direction.synthesis_for(i, model, base_settings, sensitivity)
        i["synthesis"] = syn
        i["billedChars"] = len(syn["text"])
        prepared.append(i)
    total = sum(i["billedChars"] for i in prepared)
    L = Ledger(project)
    svc = L.service("elevenlabs")
    if not svc or not svc.get("approved"):
        print(f"REFUSED: ElevenLabs is not approved at the Spend Gate ({total} characters needed). Approve with: python tools/ledger.py --project {project} approve --service elevenlabs --ceiling {total} --unit chars", file=sys.stderr)
        return 4
    pc = PaidCall(project, "elevenlabs", "chars")
    for it in items:
        out = os.path.join(project, it["file"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        syn = it["synthesis"]
        key_id = f"elevenlabs:{it.get('takeId') or it['short'] + '_' + it['kind']}:{sha256_text(syn['text'] + '|' + json.dumps(syn['settings'], sort_keys=True) + '|' + voice_id + '|' + model)[:10]}"
        part = out + ".mp3.part"

        def submit(_k, it=it, part=part):
            audio, rid = el.tts(voice_id, it["synthesis"]["text"], it["synthesis"]["settings"])
            with open(part, "wb") as f:
                f.write(audio)
            return rid

        def poll(job, part=part, it=it, key_id=key_id):
            # ElevenLabs text-to-speech answers synchronously, so a submitted job's audio is either on disk already or in the provider's
            # history. If neither has it, the audio is lost and waiting cannot bring it back: say so instead of polling until the timeout.
            if os.path.exists(part):
                return part
            if recover(key_id, it, part):
                return part
            raise Refused(6, f"{key_id}: request {job} was accepted but its audio is neither on disk nor in the provider's history; check the provider's dashboard, then `ledger.py resolve --key {key_id} --abandon` to allow one new attempt")

        def fetch(res, out=out):
            to_wav(res, out)
            os.unlink(res)
            return it["file"]

        def recover(_k, it=it, part=part):
            since = int(os.path.getmtime(L.path)) - 3600 if os.path.exists(L.path) else 0
            hid = el.find_in_history(voice_id, it["synthesis"]["text"], since)
            if hid:
                with open(part, "wb") as f:
                    f.write(el.history_audio(hid))
            return hid

        try:
            r = pc.run(key_id, it["billedChars"], submit, poll, fetch, recover)
        except Refused as e:
            print(f"REFUSED: {e.msg}", file=sys.stderr)
            return e.code
        except urllib.error.HTTPError as e:
            print(f"ElevenLabs HTTP {e.code}: {e.read()[:200]!r}", file=sys.stderr)
            if e.code in (400, 401, 403, 404, 422):
                e.never_sent = True  # the provider rejected it before generating anything
                L.failed(key_id, f"HTTP {e.code}")
            return 4
        print(("reused " if r["reused"] else "synthesised ") + it["file"])
    return 0


def sample(a, P):
    stack = a.stack or "flite"
    out = P(a.sample_out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    text = a.sample.strip()
    if stack == "flite":
        if not voice_flite.available():
            print("BLOCKED: this ffmpeg has no libflite filter; no free voice sample can be made", file=sys.stderr)
            return 3
        voice_flite.synth(text, out, a.voice, "steady", 0)
    elif stack == "elevenlabs":
        it_s = {"takeId": "sample", "file": a.sample_out, "text": text, "chars": len(text), "kind": "take", "sceneIds": [], "intensity": a.sample_intensity, "emotion": a.sample_emotion, "pace": "steady"}
        vid_s, model_s, bset_s, _ = voice_direction.resolve_elevenlabs(a.project, a.voice_id, a.model_arg)
        if not vid_s:
            print("BLOCKED: no ElevenLabs voice id (config.json voice.elevenlabs.voiceId, ELEVENLABS_VOICE_ID or --voice-id); nothing was requested", file=sys.stderr)
            return 3
        rc = synth_elevenlabs(a.project, [it_s], vid_s, model_s, a.base_url, bset_s)
        if rc:
            return rc
    else:
        print("--sample works with --stack flite or elevenlabs", file=sys.stderr)
        return 2
    print(f"voice sample ({stack}, {len(text)} chars, {duration_s(out):.1f}s) -> {a.sample_out}")
    return 0


# ───────────────────────────── main ─────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--stack", choices=["flite", "file", "elevenlabs"])
    ap.add_argument("--voice", default="slt")
    ap.add_argument("--voice-id")
    ap.add_argument("--model", dest="model_arg", default=None, help="default: config.json voice.elevenlabs.model, else eleven_multilingual_v2")
    ap.add_argument("--base-url", default=os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io"))
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--sample", help="synthesise just this text (the preview gate's voice sample); free with flite, spend-gated and ledgered with elevenlabs")
    ap.add_argument("--sample-out", default="review/preview/voice-sample.wav")
    ap.add_argument("--sample-intensity", type=int, default=0)
    ap.add_argument("--sample-emotion", default="neutral-clear")
    a = ap.parse_args()
    P = lambda *p: os.path.join(a.project, *p)  # noqa: E731
    if a.sample:
        return sample(a, P)
    sc = read_json(P("scenes.json"))
    stack = a.stack or "flite"
    takes = plan_takes(sc["scenes"], stack)
    lines = short_lines(a.project)
    write_json(P("audio", "take-plan.json"), {"stack": stack, "takes": takes, "shortLines": lines, "note": "text is what the synthesiser receives (respellings applied); captions use scenes.json narration", "totalChars": sum(t["chars"] for t in takes) + sum(l["chars"] for l in lines)})
    if a.plan_only:
        print(f"take plan: {len(takes)} takes, {sum(t['chars'] for t in takes)} chars, {len(lines)} Short lines ({sum(l['chars'] for l in lines)} chars) -> {P('audio', 'take-plan.json')}")
        return 0
    if not a.stack:
        ap.error("--stack is required unless --plan-only")
    items = [{**t, "kind": "take"} for t in takes] + lines
    os.makedirs(P("audio", "takes"), exist_ok=True)
    if stack == "flite":
        if not voice_flite.available():
            print("BLOCKED: this ffmpeg has no libflite filter; use --stack file (bring your own narration) or --stack elevenlabs", file=sys.stderr)
            return 3
        for it in items:
            out = P(it["file"])
            os.makedirs(os.path.dirname(out), exist_ok=True)
            pace, inten = (it.get("pace", "steady"), it.get("intensity", 0))
            voice_flite.synth(it["text"], out, a.voice, pace, inten)
            print("synthesised", it["file"])
        ident = {"stack": "flite", "voice": a.voice, "model": "flite (ffmpeg libflite)", "quality": "robotic; no emotion; for pipeline tests, drafts and the free path"}
    elif stack == "file":
        missing = [it["file"] for it in items if not os.path.exists(P(it["file"]))]
        if missing:
            print("BLOCKED: these files are missing (generate each text from audio/take-plan.json with any voice, save as wav/mp3-converted wav):\n  " + "\n  ".join(missing), file=sys.stderr)
            return 3
        for it in items:
            if duration_s(P(it["file"])) < 0.15:
                print(f"{it['file']} is empty", file=sys.stderr)
                return 2
        ident = {"stack": "file", "voice": "externally supplied", "model": "unknown", "quality": "as supplied"}
    else:
        vid, model, bset, src = voice_direction.resolve_elevenlabs(a.project, a.voice_id, a.model_arg)
        if not vid:
            print('BLOCKED: no ElevenLabs voice id. Put it in config.json as {"voice": {"elevenlabs": {"voiceId": "...", "model": "eleven_multilingual_v2"}}}, or set ELEVENLABS_VOICE_ID, or pass --voice-id (nothing was requested or charged)', file=sys.stderr)
            return 3
        sens = (read_json(P("config.json")).get("sensitivity", "normal") if os.path.exists(P("config.json")) else "normal")
        rc = synth_elevenlabs(a.project, items, vid, model, a.base_url, bset, sens)
        if rc:
            return rc
        ident = {"stack": "elevenlabs", "voice": vid, "voiceSource": src, "model": model, "baseSettings": {**voice_direction.BASE, **bset}, "quality": "as the provider returns; judge by ear"}
        take_plan = json.load(open(P("audio", "take-plan.json")))
        for t_ in take_plan["takes"]:
            t_["synthesis"] = next((i["synthesis"] for i in items if i.get("takeId") == t_["takeId"]), None)
        write_json(P("audio", "take-plan.json"), take_plan)
    write_json(P("audio", "takes.json"), [{"takeId": t["takeId"], "file": t["file"], "sceneIds": t["sceneIds"], "chars": t["chars"], "textSha256": sha256_text(t["text"]), "audioSha256": sha256_file(P(t["file"]))} for t in takes])
    write_json(P("audio", "voice.json"), {**ident, "takes": len(takes), "shortLines": [{k: l[k] for k in ("short", "kind", "file", "chars")} for l in lines], "totalChars": sum(t["chars"] for t in takes) + sum(l["chars"] for l in lines)})
    cont = voice_direction.continuity(a.project, takes)
    write_json(P("audio", "voice-continuity.json"), cont)
    for f in cont["findings"]:
        print(f"WARN voice continuity {f['takeId']}: {f['kind']}: {f['detail']}")
    print(f"voice stack {ident['stack']}: {len(takes)} takes + {len(lines)} Short lines -> {P('audio', 'takes.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
