"""plan_lib.py - constants and helpers shared by make_plan.py, make_allow.py and captions.py."""
import re

# default duration of each transition type in ms (reference/transition-grammar.md); a scene may set durationMs
DEFAULT_MS = {"cut": 0, "dissolve": 500, "match_geometry": 900, "match_movement": 900, "nested_scale": 1800,
              "occlusion_reveal": 800, "depth_through_object": 1200, "focus_bridge": 700, "truthful_morph": 1400}
RES = {"1080p": (1920, 1080), "1440p": (2560, 1440), "2160p": (3840, 2160)}


def caption_chunks(words, max_words=7, max_s=4.0, break_after=(".", "!", "?", ";", ":", ","), min_words=2):
    """Group aligned words into caption phrases. words: [{w,s,e,sceneId}]. Breaks at sentence punctuation, at scene
    boundaries, after max_words and when a phrase would exceed max_s. Returns [{startS,endS,text,words:[{w,s,e}]}]."""
    out, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            out.append({"startS": round(cur[0]["s"], 3), "endS": round(cur[-1]["e"], 3), "text": " ".join(x["w"] for x in cur), "words": [{"w": x["w"], "s": round(x["s"], 3), "e": round(x["e"], 3)} for x in cur]})
            cur = []

    for i, w in enumerate(words):
        if cur and (w["sceneId"] != cur[-1]["sceneId"] or len(cur) >= max_words or w["e"] - cur[0]["s"] > max_s):
            flush()
        cur.append(w)
        hard = re.search(r"[.!?]$", w["w"])
        soft = re.search(r"[;:,]$", w["w"]) and len(cur) >= max(min_words, max_words - 3)
        if hard or soft:
            flush()
    flush()
    # avoid one-word orphans: merge a lone word into the previous phrase when they are adjacent and short
    merged = []
    for c in out:
        if merged and len(c["words"]) == 1 and len(merged[-1]["words"]) < max_words and c["startS"] - merged[-1]["endS"] < 0.35 and not re.search(r"[.!?]$", merged[-1]["text"]):
            m = merged[-1]
            m["words"] += c["words"]
            m["text"] += " " + c["text"]
            m["endS"] = c["endS"]
        else:
            merged.append(c)
    return merged


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def to_srt(chunks, min_gap=0.0):
    lines = []
    for i, c in enumerate(chunks, 1):
        text = c["text"]
        if len(text) > 42:  # break into two balanced lines
            ws = text.split()
            best = min(range(1, len(ws)), key=lambda k: abs(len(" ".join(ws[:k])) - len(" ".join(ws[k:]))))
            text = " ".join(ws[:best]) + "\n" + " ".join(ws[best:])
        end = max(c["endS"], c["startS"] + 0.6)
        lines.append(f"{i}\n{srt_time(c['startS'])} --> {srt_time(end)}\n{text}\n")
    return "\n".join(lines)


def picture_region(tokens, layout):
    """The part of the frame without captions, so a still picture is not hidden by moving karaoke words (fractions of the frame).
    None when captions sit in the middle. Written into the render plan, so the renderer's own motion probe and the QA crop the same area."""
    cap = (tokens or {}).get("caption", {})
    pos = cap.get("position", "bottom")
    if pos == "center":
        return None
    safe = ((tokens or {}).get("safe", {}) or {}).get(layout, {}) or {"bottom": 0.18 if layout == "portrait" else 0.08}
    size = cap.get("sizeAt1080", 54)
    h_ref = 1080 if layout == "landscape" else 1920  # frame height when the short side is 1080 px
    zone = safe.get("bottom", 0.08) + (0.08 if pos == "lower_third" else 0.0) + 2 * 1.22 * size / h_ref + 0.02
    return {"x": 0.0, "y": 0.0, "w": 1.0, "h": round(max(0.3, 1 - zone), 3)}
