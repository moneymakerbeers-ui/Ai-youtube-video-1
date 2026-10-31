"""Shared test helpers: build audio with KNOWN word times so alignment accuracy is measured against truth."""
import os, random, sys, tempfile
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import voice_flite  # noqa: E402
from common import decode_mono, norm_word, write_wav  # noqa: E402

SR = 16000
TEXT = ("Every video starts as a single idea. The idea becomes a script, the script becomes scenes, "
        "and the scenes become pictures that move. Light from the sun is a mixture of every colour, "
        "and the sky scatters the blue light most strongly.")


def truth_audio(text=TEXT, voice="slt", seed=1, tempo=(0.85, 1.25), pause_ms=(40, 420), lead_s=0.4, tail_s=0.5):
    """Synthesise every word separately with `voice`, random tempo, random pauses. Returns (audio16k, [(s,e)] truth, words)."""
    rnd = random.Random(seed)
    words = text.split()
    parts, truth, pos = [np.zeros(int(lead_s * SR), dtype=np.float32)], [], int(lead_s * SR)
    with tempfile.TemporaryDirectory() as td:
        for i, w in enumerate(words):
            f = os.path.join(td, "w.wav")
            t = rnd.uniform(*tempo)
            p = rnd.choice([1.0, 1.0, 1.05, 0.95])
            # synthesise at natural speed then change tempo with rubberband (as a different 'speaker rate')
            from common import run
            raw = os.path.join(td, "raw.wav")
            voice_flite.synth(norm_word(w) or "um", raw, voice=voice, sr=SR)
            run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", raw, "-af", f"rubberband=tempo={t}:pitch={p}", "-ar", str(SR), "-ac", "1", f])
            x = decode_mono(f, SR)
            # trim edge silence so truth = voiced span
            e = 20 * np.log10(np.abs(x) + 1e-6)
            keep = np.where(e > e.max() - 40)[0]
            x = x[keep[0] : keep[-1] + 1]
            parts.append(x)
            truth.append((pos / SR, (pos + len(x)) / SR))
            pos += len(x)
            if i < len(words) - 1:
                gap = np.zeros(int(rnd.uniform(*pause_ms) / 1000 * SR), dtype=np.float32)
                parts.append(gap)
                pos += len(gap)
    parts.append(np.zeros(int(tail_s * SR), dtype=np.float32))
    return np.concatenate(parts), truth, words
