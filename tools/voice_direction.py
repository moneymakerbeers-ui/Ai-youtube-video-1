"""voice_direction.py - turns scenes[].voice (emotion, intensity, pace, emphasis) into what a synthesiser can actually be told, and checks
that the narrator stays the same person across takes.

ElevenLabs model families (what each can take; verify against the provider's documentation before a paid run - this file encodes what was
read on 30 Oct 2026, and only the request shape is tested, against tests/mock_elevenlabs.py; whether the audio really sounds as directed is UNTESTED):
  v2-class (eleven_multilingual_v2, eleven_turbo_v2_5, eleven_flash_*)  voice_settings: stability, similarity_boost, style, speed, use_speaker_boost.
        No inline emotion tags. Delivery is steered by stability (lower = more expressive), style (exaggeration) and speed.
  v3-class (eleven_v3*)  accepts bracketed audio tags in the text ([calm], [excited] ...); stability is one of 0.0 / 0.5 / 1.0 (creative / natural / robust).
Narrator identity stays fixed: similarity_boost, speaker boost and the voice id never change inside a video; only stability, style, speed
(v2) or the tag and stability step (v3) move, inside a narrow band, and only as far as the scene's intensity (already capped by sensitivity).
"""
import json, os, re

DEFAULT_MODEL = "eleven_multilingual_v2"
BASE = {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "speed": 1.0, "use_speaker_boost": True}
V3_TAGS = {"neutral-clear": "", "warm": "[warmly]", "curious": "[curious]", "wonder": "[with wonder]", "concern": "[seriously]", "serious": "[seriously]", "calm": "[calmly]", "excited": "[excited]", "playful": "[playfully]", "sad": "[softly]", "urgent": "[urgently]"}
PACE = {"slower": 0.92, "steady": 1.0, "faster": 1.08}
STAB = {0: 0.62, 1: 0.52, 2: 0.40, 3: 0.30}
STYLE = {0: 0.0, 1: 0.12, 2: 0.30, 3: 0.45}


def is_v3(model):
    return str(model).startswith("eleven_v3")


def synthesis_for(take, model, base=None, sensitivity="normal"):
    """What to send for one take: {"text", "settings", "tag", "notes"}. Pure function of the take, the model and the base settings."""
    base = {**BASE, **(base or {})}
    cap = {"normal": 3, "care": 2, "high": 1}.get(sensitivity, 3)
    inten = min(int(take.get("intensity", 0)), cap)
    emotion, pace = take.get("emotion", "neutral-clear"), take.get("pace", "steady")
    notes = []
    if is_v3(model):
        tag = V3_TAGS.get(emotion, "") if inten > 0 else ""
        if emotion not in V3_TAGS:
            notes.append(f"emotion '{emotion}' has no tag in the table; sent untagged")
        step = 0.0 if inten >= 3 else (0.5 if inten >= 1 else 1.0)
        settings = {"stability": step, "similarity_boost": base["similarity_boost"], "use_speaker_boost": base["use_speaker_boost"]}
        text = (tag + " " + take["text"]).strip() if tag else take["text"]
        return {"text": text, "settings": settings, "tag": tag, "notes": notes}
    stab = round(min(base["stability"], STAB[inten]) if inten else base["stability"], 3)
    settings = {"stability": stab, "similarity_boost": base["similarity_boost"], "style": round(max(base["style"], STYLE[inten]), 3),
                "speed": round(base["speed"] * PACE.get(pace, 1.0), 3), "use_speaker_boost": base["use_speaker_boost"]}
    if take.get("emphasis"):
        notes.append("emphasis words cannot be forced on this model family; they are kept for the captions and the human review only")
    return {"text": take["text"], "settings": settings, "tag": "", "notes": notes}


def resolve_elevenlabs(project, cli_id=None, cli_model=None):
    """voice id and model: command line > config.json voice.elevenlabs > ELEVENLABS_VOICE_ID / ELEVENLABS_MODEL. Returns (id, model, base, source)."""
    cfg = {}
    p = os.path.join(project, "config.json")
    if os.path.exists(p):
        cfg = (json.load(open(p)).get("voice") or {}).get("elevenlabs") or {}
    vid = cli_id or cfg.get("voiceId") or os.environ.get("ELEVENLABS_VOICE_ID")
    model = cli_model or cfg.get("model") or os.environ.get("ELEVENLABS_MODEL") or DEFAULT_MODEL
    src = "command line" if cli_id else ("config.json voice.elevenlabs" if cfg.get("voiceId") else ("ELEVENLABS_VOICE_ID" if vid else None))
    return vid, model, cfg.get("baseSettings") or {}, src


def _wav(path, sr=16000):
    import subprocess, numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[-200:])
    return np.frombuffer(r.stdout, dtype="float32"), sr


def measure(path):
    """loudness of the voiced part (dBFS RMS over frames above -45 dBFS) and median pitch (autocorrelation, 70-300 Hz) of one take."""
    import numpy as np
    x, sr = _wav(path)
    n = int(0.04 * sr)
    frames = [x[i:i + n] for i in range(0, len(x) - n, n)]
    rms = np.array([np.sqrt(np.mean(f ** 2) + 1e-12) for f in frames])
    db = 20 * np.log10(rms + 1e-9)
    voiced = db > -45
    loud = float(np.mean(db[voiced])) if voiced.any() else -90.0
    f0s = []
    lo, hi = int(sr / 300), int(sr / 70)
    for f, ok in zip(frames, voiced):
        if not ok or len(f) < hi + 2:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        if ac[0] <= 0:
            continue
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] / ac[0] > 0.45:
            f0s.append(sr / k)
    return {"loudDb": round(loud, 2), "f0Hz": round(float(np.median(f0s)), 1) if len(f0s) >= 5 else None, "voicedFrames": int(voiced.sum()), "pitchFrames": len(f0s)}


def continuity(project, takes, max_db=3.0, max_pitch=0.25):
    """Compare each take with the median of all takes. A take that is louder/quieter than max_db or whose pitch is off by more than max_pitch
    (relative) is reported: it may be a different-sounding narrator. Heuristic: a warning for a person to listen to, never a pass/fail proof."""
    import statistics
    rows = []
    for t in takes:
        try:
            m = measure(os.path.join(project, t["file"]))
        except Exception as e:  # noqa: BLE001
            rows.append({"takeId": t["takeId"], "error": str(e)[:160]})
            continue
        rows.append({"takeId": t["takeId"], **m, "intensity": t.get("intensity"), "emotion": t.get("emotion")})
    ok = [r for r in rows if "loudDb" in r]
    findings = []
    if len(ok) >= 2:
        ml = statistics.median(r["loudDb"] for r in ok)
        pf = [r["f0Hz"] for r in ok if r["f0Hz"]]
        mp = statistics.median(pf) if pf else None
        for r in ok:
            if abs(r["loudDb"] - ml) > max_db:
                findings.append({"takeId": r["takeId"], "kind": "level_jump", "detail": f"{r['loudDb'] - ml:+.1f} dB against the median take; the mix normalises the whole file, not each take"})
            if mp and r["f0Hz"] and abs(r["f0Hz"] - mp) / mp > max_pitch:
                findings.append({"takeId": r["takeId"], "kind": "pitch_jump", "detail": f"median pitch {r['f0Hz']} Hz vs {mp:.0f} Hz across takes ({(r['f0Hz'] - mp) / mp:+.0%}); listen: is it still the same narrator?"})
    return {"takes": rows, "findings": findings, "thresholds": {"maxDb": max_db, "maxPitchRel": max_pitch}, "kind": "heuristic"}
