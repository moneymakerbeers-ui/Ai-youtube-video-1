"""common.py - small helpers shared by the Python tools (no third-party dependency except numpy/scipy for audio).

Word rule used everywhere (TypeScript schema, plan, alignment, captions): a word is one whitespace-separated token of
the narration, punctuation attached. `norm_word` gives the form used for matching and speech synthesis.
"""
import hashlib, json, os, re, subprocess, sys
import numpy as np


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # atomic: a crash never leaves half a file


def run(cmd, check=True, timeout=None, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))[:300]}\n{r.stderr[-800:]}")
    return r


def words_of(text):
    return text.split()


def norm_word(w):
    w = w.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9']+", "", w)


def duration_s(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(r.stdout.strip())


def decode_mono(path, sr=16000):
    """Decode any audio file to a mono float32 array at `sr` through ffmpeg; raises if ffmpeg fails or returns nothing."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"could not decode {path}: {r.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def write_wav(path, x, sr):
    from scipy.io import wavfile

    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    y = np.clip(x, -1.0, 1.0)
    wavfile.write(path, sr, (y * 32767.0).astype(np.int16))


def load_scenes(path):
    return read_json(path)


def script_words(scenes_doc):
    """[(scene_id, word)] over the whole narration in order. The global word index is the position in this list."""
    out = []
    for s in scenes_doc["scenes"]:
        for w in words_of(s["narration"]):
            out.append((s["id"], w))
    return out


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ───────────── creative preview gate (shared by preview.py and pipeline.py) ─────────────
def creative_fingerprint(project):
    """What the creator approves at the preview gate: the look (style tokens), the voice direction, and the structure (scene ids with their outgoing
    transition types and the aspect ratios). Narration wording, layouts and timing may still be corrected by the QA loop without a new approval;
    changing the look, the voice or the structure needs one."""
    P = lambda *x: os.path.join(project, *x)  # noqa: E731
    sc = read_json(P("scenes.json"))
    tokens = read_json(P("style-tokens.json")) if os.path.exists(P("style-tokens.json")) else {}
    cfg = read_json(P("config.json")) if os.path.exists(P("config.json")) else {}
    doc = {"tokens": tokens, "voiceProfile": cfg.get("voiceProfile"), "creativeStyle": cfg.get("creativeStyle"),
           "scenes": [[s["id"], (s.get("transition") or {}).get("type", "cut"), sorted((s.get("layouts") or {}).keys())] for s in sc["scenes"]]}
    return sha256_text(json.dumps(doc, sort_keys=True, ensure_ascii=False))


def preview_gate(project):
    """(ok, message). ok when config.previewGate is not 'required', or when the creator approved the current creative fingerprint."""
    cfgp = os.path.join(project, "config.json")
    cfg = read_json(cfgp) if os.path.exists(cfgp) else {}
    if cfg.get("previewGate", "off") != "required":
        return True, "preview gate not required for this project"
    stp = os.path.join(project, "state.json")
    g = (read_json(stp) if os.path.exists(stp) else {}).get("previewGate") or {}
    if not g.get("approved"):
        return False, "the creator has not approved the creative preview yet: run `python tools/preview.py make --project <dir>`, show review/preview/ to the creator, then `python tools/preview.py approve --project <dir>`"
    if g.get("fingerprint") != creative_fingerprint(project):
        return False, "the look, voice direction or scene structure changed after the creator approved the preview: make a new preview and ask again (`preview.py make`, then `preview.py approve`)"
    return True, f"creative preview approved {g.get('at', '')}"
