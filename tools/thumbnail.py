#!/usr/bin/env python3
"""thumbnail.py - honest thumbnails built by code from the video's own frames.

  python tools/thumbnail.py --project videos/<slug> --text "ATOMS ARE WAVES" [--times 6.5,9.0] [--out out/thumbnail-1.jpg ...] [--shorts]

For each time (default: the plan's three most visually weighty moments) the engine renders that exact frame of the final plan, the caption band is cropped
away (plan.pictureRegion), the picture is fitted to 1280x720 and ONE headline of at most 3 words is set on a dark scrim in the style's display font.
Nothing is generated and nothing is invented: it is a frame of the video, so the promise is the video's. Checks written to the report: size 1280x720,
JPEG under 2 MB (YouTube's limit), at most 3 words, headline contrast >= 4.5:1 against its scrim, headline height >= 9 % of the image.
Exit: 0 written · 1 a check failed · 2 bad input · 3 the engine could not render the frame.
"""
import argparse, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_json, write_json  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1280, 720


def lum(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else (((v / 255 + 0.055) / 1.055) ** 2.4)  # noqa: E731
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--times", help="comma-separated seconds into the long video (default: three moments chosen from the plan)")
    ap.add_argument("--out", nargs="*")
    a = ap.parse_args()
    from PIL import Image, ImageDraw, ImageFont
    P = os.path.abspath(a.project)
    words = a.text.split()
    if not 1 <= len(words) <= 3:
        print(f"the headline must be 1-3 words, got {len(words)}: {a.text!r}", file=sys.stderr)
        return 2
    plan_f = os.path.join(P, "render", "plan-long.json")
    if not os.path.exists(plan_f):
        print("render/plan-long.json is missing: run the pipeline first", file=sys.stderr)
        return 2
    plan = read_json(plan_f)
    fps = plan["fps"]
    if a.times:
        times = [float(x) for x in a.times.split(",")]
    else:  # the late part of the three scenes with the most entities: everything has arrived, the picture is complete
        ranked = sorted(plan["scenes"], key=lambda s: -len(s["entities"]))[:3]
        times = [round(s["startS"] + 0.85 * (s["endS"] - s["startS"]), 3) for s in sorted(ranked, key=lambda s: s["startS"])]
    frames = [min(int(round(t * fps)), plan["durationFrames"] - 1) for t in times]
    fdir = os.path.join(P, "render", "thumbs")
    os.makedirs(fdir, exist_ok=True)
    r = subprocess.run(["npx", "tsx", "engine/render.ts", "--project", P, "--target", "long", "--dump-frames", ",".join(map(str, frames)), "--dump-dir", fdir, "--audio", "none"], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        print(f"the engine could not render the frames (exit {r.returncode}):\n{(r.stdout + r.stderr)[-600:]}", file=sys.stderr)
        return 3
    tokens = read_json(os.path.join(P, "style-tokens.json"))
    font_file = next((os.path.join(P, f["file"]) for f in tokens["fonts"]["files"] if f.get("weight", 400) >= 800), None) or os.path.join(P, tokens["fonts"]["files"][-1]["file"])
    region = plan.get("pictureRegion") or {"x": 0, "y": 0, "w": 1, "h": 1}
    outs = a.out or [os.path.join("out", f"thumbnail-{i + 1}.jpg") for i in range(len(frames))]
    os.makedirs(os.path.join(P, "out"), exist_ok=True)
    report, bad = [], 0
    for f, o in zip(frames, outs):
        im = Image.open(os.path.join(fdir, f"long-f{f:06d}.png")).convert("RGB")
        x0, y0 = int(region["x"] * im.width), int(region["y"] * im.height)
        im = im.crop((x0, y0, x0 + int(region["w"] * im.width), y0 + int(region["h"] * im.height)))
        s = max(W / im.width, H / im.height)  # cover
        im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
        im = im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
        d = ImageDraw.Draw(im, "RGBA")
        size = 150
        while True:
            font = ImageFont.truetype(font_file, size)
            tw = max(d.textlength(w, font=font) for w in [" ".join(words)])
            if tw <= W * 0.86 or size <= 60:
                break
            size -= 6
        asc, desc = font.getmetrics()
        th = asc + desc
        bx0, by1 = int(W * 0.05), H - int(H * 0.06)
        scrim = (8, 10, 16)
        d.rounded_rectangle((bx0 - 24, by1 - th - 28, bx0 + tw + 24, by1 + 12), radius=18, fill=scrim + (205,))
        d.text((bx0, by1 - th - 8), " ".join(words), font=font, fill=(255, 255, 255, 255))
        dst = o if os.path.isabs(o) else os.path.join(P, o)
        im.save(dst, "JPEG", quality=90, optimize=True)
        kb = os.path.getsize(dst) / 1024
        cap = int(by1 - th - 8)
        checks = {"size": im.size == (W, H), "underTwoMB": kb < 2048, "words": len(words) <= 3, "contrast": ratio((255, 255, 255), scrim) >= 4.5, "headlineHeight": (asc / H) >= 0.09}
        ok = all(checks.values())
        bad += not ok
        report.append({"file": os.path.relpath(dst, P), "kb": round(kb), "headlinePx": size, "checks": checks, "ok": ok})
        print(f"{'ok  ' if ok else 'FAIL'} {os.path.relpath(dst, P)}  {kb:.0f} KB  headline {size}px  " + ("" if ok else str([k for k, v in checks.items() if not v])))
    write_json(os.path.join(P, "review", "thumbnails.json"), {"text": a.text, "times": times, "thumbnails": report})
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
