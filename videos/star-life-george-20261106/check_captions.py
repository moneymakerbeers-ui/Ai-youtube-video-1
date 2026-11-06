#!/usr/bin/env python3
"""check_captions.py — the brief's caption gates, measured on the DELIVERED files (not on the plan alone):
  1 first caption at 0:00 (SRT entry 1 starts at 00:00:00,000) and the voice audibly starts at 0:00 (onset in the mp4's own audio)
  2 no caption overlaps (each SRT entry ends at or before the next one starts)
  3 audio/caption drift <= 80 ms: an INDEPENDENT recognition pass (faster-whisper medium.en; the alignment used small.en on the
    narration take) is run on the audio track extracted from the mp4, so mixing, encoding and muxing offsets are all included. Each
    recognised word is matched to the plan's word (the timing the burned-in captions and the SRT use); drift = recognised start - caption
    start. Single-word recogniser timestamps are noisy (tens of ms), so the gate is on SYSTEMATIC drift: the median offset in every 20 s
    window must be within +-80 ms. Per-word spread (p90 |d|) is reported as well, never hidden.
Writes qa/captions-<target>.json. Exit 0 = all pass, 1 = a measured failure, 3 = BLOCKED (a measurement could not run or covered too little).
usage: python3 check_captions.py [targets…]   (default: long S01 S02 S03 S04 S05)"""
import difflib, json, os, re, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from align import _wnorm  # noqa: E402

P = lambda *p: os.path.join(HERE, *p)  # noqa: E731
DRIFT_MAX = 0.080
WINDOW = 20.0


def srt_entries(path):
    out = []
    for blk in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip()):
        ls = blk.strip().splitlines()
        if len(ls) < 2:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", ls[1])
        if not m:
            raise ValueError(f"bad SRT timing line: {ls[1]!r}")
        g = [int(x) for x in m.groups()]
        out.append({"start": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, "end": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, "text": " ".join(ls[2:])})
    return out


def audio16k(mp4):
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", mp4, "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32)


def onset(x, thr_db=-40.0, hop=160):
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    i = int(np.argmax(db > thr_db)) if (db > thr_db).any() else -1
    return None if i < 0 else i * hop / 16000


_M = {}


def model():
    if "m" not in _M:
        from faster_whisper import WhisperModel
        _M["m"] = WhisperModel("medium.en", device="cpu", compute_type="int8")
    return _M["m"]


def check(t):
    mp4 = P("out", "full-video.mp4" if t == "long" else f"short-{t[1:].zfill(2)}.mp4")
    srt = P("out", "captions.srt" if t == "long" else f"short-{t[1:].zfill(2)}.srt")
    plan = json.load(open(P("render", f"plan-{t}.json")))
    res = {"target": t, "mp4": os.path.relpath(mp4, HERE), "srt": os.path.relpath(srt, HERE), "checks": {}}
    for f in (mp4, srt):
        if not os.path.exists(f):
            res["verdict"] = "BLOCKED"; res["cause"] = f"missing {f}"; return res
    caps = srt_entries(srt)
    pc = plan["captions"]
    # 1 first caption and voice onset
    x = audio16k(mp4)
    on = onset(x)
    res["checks"]["firstCaption"] = {"startS": caps[0]["start"], "ok": caps[0]["start"] <= 0.001}
    res["checks"]["voiceOnset"] = {"onsetS": on, "thresholdDbfs": -40, "ok": on is not None and on <= 0.10}
    # 2 overlaps (SRT, and SRT == plan phrases so the burned-in text and the file agree)
    ov = [{"i": i + 1, "end": a["end"], "nextStart": b["start"]} for i, (a, b) in enumerate(zip(caps, caps[1:])) if b["start"] < a["end"] - 1e-6]
    # the SRT writer (plan_lib.to_srt) keeps a phrase up for at least 0.6 s; starts must be identical, ends equal to max(plan end, start + 0.6)
    same = len(caps) == len(pc) and all(abs(a["start"] - b["startS"]) <= 0.0015 and abs(a["end"] - max(b["endS"], b["startS"] + 0.6)) <= 0.0015 for a, b in zip(caps, pc))
    res["checks"]["overlaps"] = {"count": len(ov), "first": ov[:5], "ok": not ov}
    res["checks"]["srtMatchesBurnedIn"] = {"srtEntries": len(caps), "planPhrases": len(pc), "ok": same}
    # 3 drift against an independent recognition of the delivered audio
    segs, _ = model().transcribe(x, language="en", word_timestamps=True, condition_on_previous_text=False, vad_filter=False, beam_size=5)
    rec = [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if w.word.strip()]
    pw = plan["words"]
    A = [_wnorm(w["w"]).replace("-", "") for w in pw]
    B = [_wnorm(w[0]).replace("-", "") for w in rec]
    sm = difflib.SequenceMatcher(a=A, b=B, autojunk=False)
    pairs = []
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pairs.append((pw[blk.a + k]["s"], rec[blk.b + k][1]))
    cover = len(pairs) / max(1, len(pw))
    d = np.array([r - c for c, r in pairs]) if pairs else np.array([])
    wins = []
    dur = plan["durationS"]
    w0 = 0.0
    while w0 < dur - 1e-6:
        sel = [r - c for c, r in pairs if w0 <= c < w0 + WINDOW]
        if len(sel) >= 8:
            wins.append({"fromS": round(w0, 1), "toS": round(min(w0 + WINDOW, dur), 1), "n": len(sel), "medianDriftMs": round(1000 * float(np.median(sel)), 1)})
        w0 += WINDOW
    worst = max((abs(w["medianDriftMs"]) for w in wins), default=None)
    res["checks"]["drift"] = {
        "engine": "faster-whisper medium.en on the mp4's audio (independent of the small.en alignment)",
        "planWords": len(pw), "matched": len(pairs), "coverage": round(cover, 3),
        "overallMedianMs": round(1000 * float(np.median(d)), 1) if len(d) else None,
        "p90AbsMs": round(1000 * float(np.percentile(np.abs(d), 90)), 1) if len(d) else None,
        "windows": wins, "worstWindowMedianMs": worst, "limitMs": DRIFT_MAX * 1000,
        "ok": bool(cover >= 0.85 and wins and worst is not None and worst <= DRIFT_MAX * 1000),
    }
    blocked = cover < 0.85 or not wins
    oks = [c["ok"] for c in res["checks"].values()]
    res["verdict"] = "BLOCKED" if blocked else ("PASSED" if all(oks) else "FAILED")
    if blocked:
        res["cause"] = f"independent recognition matched only {cover:.0%} of the caption words"
    return res


def main():
    os.makedirs(P("qa"), exist_ok=True)
    worst = 0
    for t in (sys.argv[1:] or ["long", "S01", "S02", "S03", "S04", "S05"]):
        r = check(t)
        json.dump(r, open(P("qa", f"captions-{t}.json"), "w"), indent=1)
        c = r.get("checks", {})
        dr = c.get("drift", {})
        print(f"{t}: {r['verdict']}  first caption {c.get('firstCaption', {}).get('startS')}s · voice onset {c.get('voiceOnset', {}).get('onsetS')}s · "
              f"overlaps {c.get('overlaps', {}).get('count')} · srt==burned-in {c.get('srtMatchesBurnedIn', {}).get('ok')} · drift worst-window "
              f"{dr.get('worstWindowMedianMs')} ms (overall median {dr.get('overallMedianMs')} ms, p90 |d| {dr.get('p90AbsMs')} ms, coverage {dr.get('coverage')})"
              + (f" · {r['cause']}" if r.get("cause") else ""))
        worst = max(worst, {"PASSED": 0, "FAILED": 1, "BLOCKED": 3}[r["verdict"]])
    return worst


if __name__ == "__main__":
    sys.exit(main())
