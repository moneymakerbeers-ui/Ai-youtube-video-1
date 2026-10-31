#!/usr/bin/env python3
"""contrast.py - WCAG 2.x contrast ratios, so palette decisions are computed, not eyeballed.

usage:
  python tools/contrast.py "#f4efe6" "#1b1b1b"          # one pair
  python tools/contrast.py --tokens style-tokens.json   # every pair listed in the tokens file
tokens file: {"palette": {"bg": "#...", "ink": "#...", ...},
              "textPairs": [["ink","bg"], ...],      # need >= 4.5
              "graphicPairs": [["accent","bg"], ...]} # need >= 3.0 (lines, icons, large display text)
exit code: 0 = all pairs pass, 1 = at least one fails, 2 = usage error.
"""
import json, re, sys

TEXT_MIN, GRAPHIC_MIN = 4.5, 3.0


def parse(c):
    c = c.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}|[0-9a-fA-F]{3}", c):
        raise ValueError(f"not a hex colour: {c!r}")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = luminance(parse(a)), luminance(parse(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main(argv):
    try:
        if len(argv) == 2 and argv[0] != "--tokens":
            r = ratio(argv[0], argv[1])
            print(f"{argv[0]} on {argv[1]}: {r:.2f}:1  text {'PASS' if r >= TEXT_MIN else 'FAIL'} (>= {TEXT_MIN})  graphics {'PASS' if r >= GRAPHIC_MIN else 'FAIL'} (>= {GRAPHIC_MIN})")
            return 0 if r >= TEXT_MIN else 1
        if len(argv) == 2 and argv[0] == "--tokens":
            t = json.load(open(argv[1]))
            pal, bad = t["palette"], 0
            for kind, pairs, need in (("text", t.get("textPairs", []), TEXT_MIN), ("graphic", t.get("graphicPairs", []), GRAPHIC_MIN)):
                for fg, bg in pairs:
                    r = ratio(pal[fg], pal[bg])
                    ok = r >= need
                    bad += not ok
                    print(f"{'PASS' if ok else 'FAIL'}  {kind:7} {fg} on {bg}: {r:.2f}:1 (need {need})")
            if not t.get("textPairs"):
                print("FAIL  no textPairs listed: every text colour must be checked against its background")
                bad += 1
            return 1 if bad else 0
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as e:
        print(f"contrast.py: {e}", file=sys.stderr)
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
