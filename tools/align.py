#!/usr/bin/env python3
"""align.py - word-level timing measured on the FINAL audio file (never guessed from words-per-minute).

Engines (pick with --engine; `auto` = ALIGN_ENGINE if set, else elevenlabs if a key exists, else dtw; whisper needs faster-whisper):
  dtw          FREE, local, no model download. Synthesises a reference of the script with the local flite voice and
               warps it onto the real audio with dynamic time warping over MFCC features (the method aeneas uses).
               Accuracy is measured, not assumed: tests/test_align.py builds audio with KNOWN word times (another
               voice, other tempo, random pauses) and asserts median/p90 error. Real human or ElevenLabs speech
               is acoustically further from the flite reference, so treat the error bounds as optimistic.
  elevenlabs   ElevenLabs forced-alignment endpoint (UNTESTED live: needs ELEVENLABS_API_KEY and network).
  whisper      faster-whisper word timestamps mapped onto the script words (difflib); unmatched words interpolated (conf 0.3); fails if < 85 % match.
               Select with --engine whisper or ALIGN_ENGINE=whisper (auto never picks it implicitly). Missing package = exit 3 BLOCKED.

usage:
  python tools/align.py --audio audio/narration.wav --assembly audio/assembly.json --scenes scenes.json \
        --script spoken_script.txt --out audio/alignment.json [--engine dtw] [--project .]
  python tools/align.py --audio X.wav --text "plain words" --out Y.json          (single segment, no scenes)
Alignment is stored with the SHA-256 of the audio it measured; the validator and the planner refuse an alignment whose
audio hash no longer matches the file, so timestamps can never be silently copied from another file.
Exit codes: 0 ok, 2 usage, 3 BLOCKED (engine unavailable), 4 alignment failed its own verification.
"""
import argparse, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import decode_mono, die, duration_s, norm_word, read_json, script_words, sha256_file, sha256_text, write_json, words_of  # noqa: E402

SR = 16000
HOP = 160  # 10 ms
WIN = 400  # 25 ms
REF_VOICE = os.environ.get("ALIGN_REF_VOICE", "kal16")
GAP_S = 0.06
EDGE_S = 0.15


# ───────────────────────── features ─────────────────────────
def _mel_fb(n_mels=40, n_fft=512, sr=SR, fmin=60.0, fmax=7600.0):
    def hz2mel(f):
        return 2595.0 * np.log10(1 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1)

    pts = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, b):
            fb[m - 1, k] = (k - a) / max(b - a, 1)
        for k in range(b, c):
            fb[m - 1, k] = (c - k) / max(c - b, 1)
    return fb


_FB = None


def mfcc(x, n_mfcc=13):
    """Frames of [c0..c12] (c0 = log energy), 10 ms hop. Returned already mean/variance normalised."""
    global _FB
    from scipy.fft import dct

    if _FB is None:
        _FB = _mel_fb()
    x = np.append(x[0], x[1:] - 0.97 * x[:-1]).astype(np.float32)  # pre-emphasis
    pad = np.zeros(WIN, dtype=np.float32)
    x = np.concatenate([x, pad])
    n = 1 + (len(x) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    fr = x[idx] * np.hamming(WIN).astype(np.float32)
    spec = np.abs(np.fft.rfft(fr, 512, axis=1)) ** 2
    mel = np.log(spec @ _FB.T + 1e-8)
    c = dct(mel, type=2, axis=1, norm="ortho")[:, :n_mfcc]
    mu, sd = c.mean(0), c.std(0) + 1e-6
    return ((c - mu) / sd).astype(np.float32)


def energy_db(x):
    n = 1 + max(len(x) - WIN, 0) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    fr = np.pad(x, (0, WIN))[idx]
    return 10 * np.log10(np.mean(fr**2, axis=1) + 1e-10)


# ───────────────────────── reference voice ─────────────────────────
_CACHE = {}


def ref_word_audio(word, cache_dir):
    key = word
    if key in _CACHE:
        return _CACHE[key]
    os.makedirs(cache_dir, exist_ok=True)
    fn = os.path.join(cache_dir, f"{REF_VOICE}-{sha256_text(word)[:16]}.npy")
    if os.path.exists(fn):
        _CACHE[key] = np.load(fn)
        return _CACHE[key]
    import tempfile

    import voice_flite

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "w.wav")
        voice_flite.synth(word, out, voice=REF_VOICE, sr=SR)
        x = decode_mono(out, SR)
    # trim leading/trailing near-silence of the synthesised word
    e = energy_db(x)
    keep = np.where(e > e.max() - 35)[0]
    if len(keep):
        x = x[max(keep[0] * HOP - HOP, 0) : min(keep[-1] * HOP + WIN + HOP, len(x))]
    np.save(fn, x)
    _CACHE[key] = x
    return x


def build_reference(words, cache_dir):
    parts, bounds, pos = [np.zeros(int(EDGE_S * SR), dtype=np.float32)], [], int(EDGE_S * SR)
    gap = np.zeros(int(GAP_S * SR), dtype=np.float32)
    for i, w in enumerate(words):
        x = ref_word_audio(w, cache_dir)
        bounds.append((pos, pos + len(x)))
        parts.append(x)
        pos += len(x)
        if i < len(words) - 1:
            parts.append(gap)
            pos += len(gap)
    parts.append(np.zeros(int(EDGE_S * SR), dtype=np.float32))
    return np.concatenate(parts), bounds


# ───────────────────────── dynamic time warping (reference-driven, banded, vectorised) ─────────────────────────
STEP_COST = {0: 0.35, 1: 0.0, 2: 0.25, 3: 0.55, 4: 0.9}  # per-step penalties: strongly prefer the diagonal


def dtw_path(ref, tgt, band_s=3.0):
    """Align every reference frame i to a target frame j(i), nondecreasing, steps 0..4 target frames per reference frame.
    Returns j[i] for every i. Forced start (0,0) and end (M-1,N-1)."""
    M, N = len(ref), len(tgt)
    if N < 8 or M < 8:
        raise ValueError("audio or reference too short to align")
    W = int(max(0.2 * N, band_s * 100))
    slope = (N - 1) / max(M - 1, 1)
    INF = np.float32(1e9)
    steps = sorted(STEP_COST)
    D_prev = np.full(2 * W + 1, INF, dtype=np.float32)
    back = np.zeros((M, 2 * W + 1), dtype=np.uint8)
    centers = np.rint(np.arange(M) * slope).astype(int)

    def row_cost(i):
        c = centers[i]
        lo, hi = c - W, c + W + 1
        cols = np.arange(lo, hi)
        valid = (cols >= 0) & (cols < N)
        d = np.full(2 * W + 1, INF, dtype=np.float32)
        t = tgt[np.clip(cols, 0, N - 1)]
        diff = t - ref[i][None, :]
        dist = np.sqrt((diff * diff).sum(1)).astype(np.float32)
        d[valid] = dist[valid]
        return d, cols

    d0, cols0 = row_cost(0)
    D_prev[:] = INF
    k0 = int(np.where(cols0 == 0)[0][0])
    D_prev[k0] = d0[k0]
    prev_cols = cols0
    for i in range(1, M):
        d, cols = row_cost(i)
        shift = cols[0] - prev_cols[0]  # centre moves ~slope per row
        best = np.full(2 * W + 1, INF, dtype=np.float32)
        arg = np.zeros(2 * W + 1, dtype=np.uint8)
        for s in steps:
            # predecessor column j - s expressed in the previous row's band index
            idx = np.arange(2 * W + 1) - s + shift
            ok = (idx >= 0) & (idx < 2 * W + 1)
            cand = np.full(2 * W + 1, INF, dtype=np.float32)
            cand[ok] = D_prev[idx[ok]] + STEP_COST[s]
            better = cand < best
            best = np.where(better, cand, best)
            arg = np.where(better, s, arg).astype(np.uint8)
        D_prev = np.minimum(best + d, INF)
        back[i] = arg
        prev_cols = cols
    # forced end at column N-1
    kend = int(np.where(prev_cols == N - 1)[0][0]) if (prev_cols == N - 1).any() else int(np.argmin(D_prev))
    if D_prev[kend] >= INF / 2:
        raise RuntimeError("DTW found no path inside the band (audio and script lengths are very different)")
    j = np.zeros(M, dtype=int)
    k = kend
    cols_i = prev_cols
    for i in range(M - 1, -1, -1):
        j[i] = cols_i[k]
        if i == 0:
            break
        s = int(back[i][k])
        c_prev = centers[i - 1] - W
        j_prev = j[i] - s
        k = int(j_prev - c_prev)
        cols_i = np.arange(centers[i - 1] - W, centers[i - 1] + W + 1)
        k = int(np.clip(k, 0, 2 * W))
    cost = float(D_prev[kend]) / M
    return j, cost


def align_dtw(x, words, cache_dir, t0=0.0):
    """x: mono 16 kHz audio of ONE segment; words: list of script words. Returns [(s, e, conf)] in seconds (+t0)."""
    nw = [norm_word(w) or "um" for w in words]
    ref, bounds = build_reference(nw, cache_dir)
    fr_ref, fr_tgt = mfcc(ref), mfcc(x)
    j, cost = dtw_path(fr_ref, fr_tgt)
    en = energy_db(x)
    res = []
    for (a, b) in bounds:
        ia, ib = int(a // HOP), int(min(b // HOP, len(fr_ref) - 1))
        ta, tb = int(j[min(ia, len(j) - 1)]), int(j[min(ib, len(j) - 1)])
        seg = en[ta : tb + 1]
        # local confidence: mean frame distance along the word, mapped to 0..1 (lower distance = higher confidence)
        dm = float(np.mean(np.sqrt(((fr_tgt[np.clip(j[ia : ib + 1], 0, len(fr_tgt) - 1)] - fr_ref[ia : ib + 1]) ** 2).sum(1)))) if ib >= ia else 9.0
        conf = float(np.clip(1.2 - dm / 8.0, 0.0, 1.0))
        res.append([ta * HOP / SR, (tb + 1) * HOP / SR, conf, float(seg.max()) if len(seg) else -99.0])
    # snap each boundary to the voiced edge: DTW places a word within a few frames, the energy envelope says where speech
    # really starts and stops (only moves a boundary toward speech and never past a neighbour)
    thr = float(np.percentile(en, 92)) - 30.0
    for k in range(len(res)):
        lo = res[k - 1][1] if k else 0.0
        hi = res[k + 1][0] if k + 1 < len(res) else len(x) / SR
        fa, fb = int(max(res[k][0] - 0.12, lo) * SR / HOP), int(min(res[k][0] + 0.25, res[k][1]) * SR / HOP)
        on = np.where(en[fa : fb + 1] > thr)[0]
        if len(on):
            res[k][0] = (fa + int(on[0])) * HOP / SR
        ea, eb = int(max(res[k][1] - 0.25, res[k][0]) * SR / HOP), int(min(res[k][1] + 0.12, hi) * SR / HOP)
        on = np.where(en[ea : eb + 1] > thr)[0]
        if len(on):
            res[k][1] = (ea + int(on[-1]) + 1) * HOP / SR
    # tidy: words must not overlap and must stay inside the segment
    dur = len(x) / SR
    for k in range(len(res)):
        res[k][0] = float(np.clip(res[k][0], 0, dur))
        res[k][1] = float(np.clip(max(res[k][1], res[k][0] + 0.03), 0, dur))
        if k:
            if res[k][0] < res[k - 1][1]:
                mid = (res[k][0] + res[k - 1][1]) / 2
                res[k - 1][1], res[k][0] = mid, mid
    return [(s + t0, e + t0, c) for s, e, c, _ in res], cost


# ───────────────────────── other engines (adapters; untested here) ─────────────────────────
def align_elevenlabs(audio_path, text):
    import json, urllib.request, uuid

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise PermissionError("ELEVENLABS_API_KEY is not set")
    base = os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
    boundary = uuid.uuid4().hex
    body = b""
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="text"\r\n\r\n{text}\r\n'.encode()
    body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode() + open(audio_path, "rb").read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{base}/v1/forced-alignment", data=body, headers={"xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    return [(w["start"], w["end"], 1.0 - float(w.get("loss", 0.0))) for w in data["words"]]


_WHISPER = {}


def _whisper_model():
    """faster-whisper model, loaded once. ALIGN_WHISPER_MODEL picks the size (default small.en). Missing package = BLOCKED, never a guess."""
    name = os.environ.get("ALIGN_WHISPER_MODEL", "small.en")
    if name not in _WHISPER:
        try:
            from faster_whisper import WhisperModel  # noqa: WPS433
        except ImportError as e:
            raise ModuleNotFoundError(f"faster-whisper is not installed ({e}); pip install faster-whisper, or use --engine dtw") from e
        _WHISPER[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _WHISPER[name]


_NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
        "20": "twenty", "21": "twentyone", "25": "twentyfive", "33": "thirtythree", "40": "forty", "100": "hundred"}


def _wnorm(w):
    n = norm_word(w).replace("'", "")
    return _NUM.get(n, n)


def align_whisper(x, words, t0=0.0):
    """Recognise ONE segment (16 kHz mono) with faster-whisper word timestamps, then map the recognised words onto the SCRIPT words with a
    sequence alignment (difflib on normalised tokens; hyphenated script words are compared without the hyphen). Matched script words take the
    recognised timing and its probability as confidence; unmatched script words are interpolated between their matched neighbours by
    character count and get confidence 0.3 (listed in the notes). Returns ([(s, e, conf)], stats)."""
    import difflib

    model = _whisper_model()
    segs, _info = model.transcribe(x.astype(np.float32), language="en", word_timestamps=True, beam_size=5, vad_filter=False,
                                   initial_prompt=" ".join(words)[:800])
    rec = [(float(w.start), float(w.end), float(w.probability), w.word) for s in segs for w in (s.words or [])]
    # split recognised tokens that hold several words ("light-years" stays one, "10 million" is already two tokens)
    a = [_wnorm(w.replace("-", "")) for _, _, _, w in rec]
    b = [_wnorm(w.replace("-", "")) for w in words]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    res = [None] * len(words)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            s, e, pr, _ = rec[blk.a + k]
            res[blk.b + k] = [s, e, pr]
    # replace-blocks with equal length (e.g. "M87" vs "M87," variants) map one to one
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                s, e, pr, _ = rec[i1 + k]
                res[j1 + k] = [s, e, min(pr, 0.6)]
    matched = sum(1 for r in res if r is not None)
    dur = len(x) / SR
    # interpolate the gaps by character weight between the neighbours' edges
    k = 0
    while k < len(res):
        if res[k] is not None:
            k += 1
            continue
        j = k
        while j < len(res) and res[j] is None:
            j += 1
        lo = res[k - 1][1] if k > 0 else (rec[0][0] if rec else 0.0)
        hi = res[j][0] if j < len(res) else (rec[-1][1] if rec else dur)
        hi = max(hi, lo + 0.06 * (j - k))
        wts = [max(len(b[q]), 1) for q in range(k, j)]
        tot, acc = float(sum(wts)), lo
        for q, wq in zip(range(k, j), wts):
            span = (hi - lo) * wq / tot
            res[q] = [acc, acc + span, 0.3]
            acc += span
        k = j
    # monotonic, non-overlapping, inside the segment
    for q in range(len(res)):
        res[q][0] = float(np.clip(res[q][0], 0, dur))
        res[q][1] = float(np.clip(max(res[q][1], res[q][0] + 0.03), 0, dur))
        if q and res[q][0] < res[q - 1][1]:
            if res[q][0] < res[q - 1][0]:
                res[q][0] = res[q - 1][1]
                res[q][1] = max(res[q][1], res[q][0] + 0.03)
            else:
                mid = (res[q][0] + res[q - 1][1]) / 2
                res[q - 1][1], res[q][0] = mid, mid
    return [(s + t0, e + t0, c) for s, e, c in res], {"recognised": len(rec), "matched": matched, "scriptWords": len(words)}


# ───────────────────────── driver ─────────────────────────
def pick_engine(requested):
    if requested != "auto":
        return requested
    if os.environ.get("ALIGN_ENGINE") in ("dtw", "elevenlabs", "whisper"):
        return os.environ["ALIGN_ENGINE"]  # explicit project/run choice (e.g. whisper for a human-like voice); never implicit
    if os.environ.get("ELEVENLABS_API_KEY"):
        return "elevenlabs"
    return "dtw"  # whisper is not implemented, so `auto` never selects it even when faster-whisper happens to be installed


def verify(words, dur, text_words):
    """The checks of stage 03: coverage, monotonic, inside the file. Returns a list of problems."""
    probs = []
    if len(words) != len(text_words):
        probs.append(f"{len(words)} aligned words for {len(text_words)} script words")
    last = -1
    for w in words:
        if w["s"] < last - 1e-6:
            probs.append(f"word {w['i']} starts before the previous word")
        last = w["s"]
        if w["e"] > dur + 0.05:
            probs.append(f"word {w['i']} ends after the audio")
    return probs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--assembly")
    ap.add_argument("--scenes")
    ap.add_argument("--script", help="spoken_script.txt (written if missing when --scenes is given)")
    ap.add_argument("--text", help="plain text instead of scenes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="auto", choices=["auto", "dtw", "elevenlabs", "whisper"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()

    engine = pick_engine(a.engine)
    cache = a.cache or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "library", "cache", "ref_words")
    if not os.path.exists(a.audio):
        die(f"audio file not found: {a.audio}")
    audio_dur = duration_s(a.audio)

    if a.scenes:
        sc = read_json(a.scenes)
        sw = script_words(sc)
        text = "\n".join(s["narration"] for s in sc["scenes"]) + "\n"
        script_file = a.script or os.path.join(os.path.dirname(a.out) or ".", "spoken_script.txt")
        os.makedirs(os.path.dirname(script_file) or ".", exist_ok=True)
        open(script_file, "w", encoding="utf-8").write(text)
    else:
        text = (a.text or "").strip() + "\n"
        sw = [("-", w) for w in words_of(text)]
        script_file = a.script or os.path.join(os.path.dirname(a.out) or ".", "spoken_script.txt")
        open(script_file, "w", encoding="utf-8").write(text)
    if not sw:
        die("script has no words")

    x = decode_mono(a.audio, SR)
    notes, words_out = [], []
    try:
        if engine == "dtw":
            segs = []
            if a.assembly:
                asm = read_json(a.assembly)
                scene_words = {}
                gi = 0
                for sid, _w in sw:
                    scene_words.setdefault(sid, []).append(gi)
                    gi += 1
                for seg in asm["segments"]:
                    idxs = [i for sid in seg["sceneIds"] for i in scene_words[sid]]
                    segs.append((seg["startS"], seg["endS"], idxs))
            else:
                segs.append((0.0, audio_dur, list(range(len(sw)))))
            res = [None] * len(sw)
            costs = []
            for (s0, s1, idxs) in segs:
                pad = 0.12
                a0, a1 = max(s0 - pad, 0), min(s1 + pad, audio_dur)
                xs = x[int(a0 * SR) : int(a1 * SR)]
                r, cost = align_dtw(xs, [sw[i][1] for i in idxs], cache, t0=a0)
                costs.append(cost)
                for i, v in zip(idxs, r):
                    res[i] = v
            if any(v is None for v in res):
                raise RuntimeError("some script words are in no assembly segment")
            notes.append("dtw_reference: reference voice flite/" + REF_VOICE + "; median cost per frame " + f"{float(np.median(costs)):.2f}")
            if os.environ.get("ALIGN_REF_VOICE") is None:
                notes.append("APPROXIMATE: the reference voice is not the narrator's voice, so word boundaries inside connected speech can be off by several hundred ms (sentence and scene boundaries are reliable). Use ElevenLabs forced alignment or whisper for human-like voices.")
        elif engine == "elevenlabs":
            res = align_elevenlabs(a.audio, text)
            if len(res) != len(sw):
                raise RuntimeError(f"ElevenLabs returned {len(res)} words for {len(sw)} script words; the mapping needs review")
        else:
            segs = []
            if a.assembly:
                asm = read_json(a.assembly)
                scene_words = {}
                for gi, (sid, _w) in enumerate(sw):
                    scene_words.setdefault(sid, []).append(gi)
                for seg in asm["segments"]:
                    segs.append((seg["startS"], seg["endS"], [i for sid in seg["sceneIds"] for i in scene_words[sid]]))
            else:
                segs.append((0.0, audio_dur, list(range(len(sw)))))
            res = [None] * len(sw)
            m_tot = 0
            for (s0, s1, idxs) in segs:
                pad = 0.12
                a0, a1 = max(s0 - pad, 0), min(s1 + pad, audio_dur)
                r, st = align_whisper(x[int(a0 * SR) : int(a1 * SR)], [sw[i][1] for i in idxs], t0=a0)
                m_tot += st["matched"]
                for i, v in zip(idxs, r):
                    res[i] = v
            if any(v is None for v in res):
                raise RuntimeError("some script words are in no assembly segment")
            share = m_tot / len(sw)
            notes.append(f"whisper ({os.environ.get('ALIGN_WHISPER_MODEL', 'small.en')}, faster-whisper word timestamps) mapped onto the script: {m_tot}/{len(sw)} script words matched a recognised word ({share:.1%}); the rest are interpolated between matched neighbours (confidence 0.3)")
            if share < 0.85:
                raise RuntimeError(f"only {share:.1%} of the script words matched the recognised speech: the audio may not say the script")
    except (PermissionError, ModuleNotFoundError) as e:
        print(f"BLOCKED: engine {engine} unavailable: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: alignment engine {engine}: {e}", file=sys.stderr)
        return 4

    for i, ((sid, w), (s, e, c)) in enumerate(zip(sw, res)):
        words_out.append({"i": i, "w": w, "s": round(float(s), 3), "e": round(float(e), 3), "scene": sid if sid != "-" else None, "conf": round(float(c), 3)})
    for w in words_out:
        if w["scene"] is None:
            del w["scene"]
    probs = verify(words_out, audio_dur, sw)
    scene_bounds = []
    if a.scenes:
        order = [s["id"] for s in sc["scenes"]]
        first, last = {}, {}
        for w in words_out:
            first.setdefault(w["scene"], w["i"])
            last[w["scene"]] = w["i"]
        starts = []
        for k, sid in enumerate(order):
            if k == 0:
                starts.append(0.0)
            else:
                prev_end = words_out[last[order[k - 1]]]["e"]
                nxt = words_out[first[sid]]["s"]
                starts.append(round((prev_end + nxt) / 2, 3))  # boundary = midpoint of the silence between scenes
        for k, sid in enumerate(order):
            end = starts[k + 1] if k + 1 < len(order) else round(audio_dur, 3)
            scene_bounds.append({"sceneId": sid, "startS": starts[k], "endS": end, "firstWord": first[sid], "lastWord": last[sid]})
    confs = [w["conf"] for w in words_out]
    low = sum(1 for c in confs if c < 0.35)
    if low:
        notes.append(f"{low} words have confidence < 0.35: listen to them before trusting their timing")
    doc = {
        "version": 1,
        "source": {"dtw": "dtw_reference", "elevenlabs": "elevenlabs_forced", "whisper": "whisper"}[engine],
        "audio": {"file": os.path.relpath(a.audio, a.project), "sha256": sha256_file(a.audio), "durationS": round(audio_dur, 3)},
        "script": {"file": os.path.relpath(script_file, a.project), "sha256": sha256_file(script_file)},
        "coverage": round(len(words_out) / len(sw), 4),
        "words": words_out,
        "sceneBounds": scene_bounds,
        "quality": {"medianConf": round(float(np.median(confs)), 3), "notes": notes},
    }
    write_json(a.out, doc)
    print(f"{engine}: {len(words_out)} words, coverage {doc['coverage']:.3f}, median confidence {doc['quality']['medianConf']}, wrote {a.out}")
    for p in probs:
        print("PROBLEM:", p, file=sys.stderr)
    return 4 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
