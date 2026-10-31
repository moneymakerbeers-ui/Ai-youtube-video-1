"""audio_lib.py - assembling narration from takes with true, recorded silences (shared by assemble_audio.py and short_audio.py)."""
import os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import decode_mono, sha256_file, write_wav  # noqa: E402

SR = 24000
BASE_GAP_MS = 280  # natural breath between two takes when nothing special is declared (shorter than any silence gate)


def trim_voiced(x, sr=SR, pad_ms=40, floor_db=-46.0):
    """Cut leading/trailing near-silence (relative to the loudest frames), keeping `pad_ms` of room at each edge."""
    hop = int(sr * 0.01)
    n = max(len(x) // hop, 1)
    e = 10 * np.log10(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    keep = np.where(e > max(e.max() - 40.0, floor_db))[0]
    if not len(keep):
        return x
    a = max(keep[0] * hop - int(sr * pad_ms / 1000), 0)
    b = min((keep[-1] + 1) * hop + int(sr * pad_ms / 1000), len(x))
    return x[a:b]


def fade(x, sr=SR, ms=8):
    n = min(int(sr * ms / 1000), len(x) // 2)
    if n > 0:
        r = np.linspace(0.0, 1.0, n, dtype=np.float32)
        x = x.copy()
        x[:n] *= r
        x[-n:] *= r[::-1]
    return x


def assemble(parts, lead_ms=0, tail_ms=0, sr=SR):
    """parts: [{id, x(float32 mono at sr), gapBeforeMs, reason, declaredMs, meta}] in order.
    Returns (audio, segments, silences). Every silence is recorded with its exact span and why it exists: the plan,
    the allow-list and the QA gate all read these records instead of guessing."""
    chunks, segments, silences, pos = [], [], [], 0

    def add_silence(ms, reason, declared):
        nonlocal pos
        n = int(round(sr * ms / 1000))
        if n <= 0:
            return
        chunks.append(np.zeros(n, dtype=np.float32))
        silences.append({"fromS": round(pos / sr, 3), "toS": round((pos + n) / sr, 3), "reason": reason, "declaredMs": int(declared)})
        pos += n

    if lead_ms:
        add_silence(lead_ms, "opening lead silence", lead_ms)
    for k, p in enumerate(parts):
        if k:
            add_silence(p.get("gapBeforeMs", BASE_GAP_MS), p.get("reason", "take join"), p.get("declaredMs", 0))
        x = fade(p["x"], sr)
        segments.append({"id": p["id"], "startS": round(pos / sr, 3), "endS": round((pos + len(x)) / sr, 3), **p.get("meta", {})})
        chunks.append(x)
        pos += len(x)
    if tail_ms:
        add_silence(tail_ms, "ending tail silence", tail_ms)
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32), segments, silences


def load(path, sr=SR):
    return decode_mono(path, sr)
