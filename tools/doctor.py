#!/usr/bin/env python3
"""doctor.py - one honest inventory of what this machine can and cannot do, with evidence. Stage 00 of /make runs it.

  python tools/doctor.py [--project videos/<slug>] [--json out.json] [--net]

Every line is  AVAILABLE (a command ran and produced the expected result just now) · MISSING (a required tool is absent) ·
UNTESTED (needs an account, key or network this check does not use) · BLOCKED (checked and refused, e.g. the network allow-list).
Nothing is reported AVAILABLE from memory. --net also tries to reach the services (a refusal is reported as BLOCKED, never retried by another route).
Exit: 0 everything required is AVAILABLE · 3 something required is MISSING.
"""
import argparse, json, os, shutil, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

REQUIRED_FILTERS = ["scale", "tblend", "signalstats", "blackdetect", "silencedetect", "ebur128", "loudnorm", "metadata", "crop", "split", "overlay", "volume"]
REQUIRED_ENCODERS = ["libx264", "aac"]


def run(cmd, timeout=60, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def item(name, status, detail, required=False, how=""):
    return {"name": name, "status": status, "detail": detail, "required": required, "howToFix": how}


def check_all(project=None, net=False):
    out = []
    rc, o = run(["ffmpeg", "-hide_banner", "-version"])
    out.append(item("ffmpeg", "AVAILABLE" if rc == 0 else "MISSING", o.splitlines()[0] if rc == 0 else o.strip(), True, "install ffmpeg >= 6 (apt install ffmpeg)"))
    rc2, o2 = run(["ffprobe", "-hide_banner", "-version"])
    out.append(item("ffprobe", "AVAILABLE" if rc2 == 0 else "MISSING", o2.splitlines()[0] if rc2 == 0 else o2.strip(), True, "comes with ffmpeg"))
    if rc == 0:
        _, flt = run(["ffmpeg", "-hide_banner", "-filters"])
        have = {ln.split()[1] for ln in flt.splitlines() if len(ln.split()) > 2 and ln.startswith(" ")}
        miss = [f for f in REQUIRED_FILTERS if f not in have]
        out.append(item("ffmpeg filters (QA + render)", "AVAILABLE" if not miss else "MISSING", "all present" if not miss else "missing: " + ", ".join(miss), True, "use an ffmpeg build with these filters"))
        _, enc = run(["ffmpeg", "-hide_banner", "-encoders"])
        miss = [e for e in REQUIRED_ENCODERS if e not in enc]
        out.append(item("ffmpeg encoders", "AVAILABLE" if not miss else "MISSING", "libx264 + aac present" if not miss else "missing: " + ", ".join(miss), True, "use an ffmpeg build with libx264"))
        out.append(item("ffmpeg libflite (free local voice)", "AVAILABLE" if "flite" in have else "MISSING", "flite filter present" if "flite" in have else "no flite filter: the free voice stack is unavailable; use --stack file or elevenlabs", False, "ffmpeg built with --enable-libflite"))
        out.append(item("ffmpeg rubberband (pitch/tempo)", "AVAILABLE" if "rubberband" in have else "MISSING", "present" if "rubberband" in have else "absent: take pace changes use atempo", False, ""))
    rc, o = run(["node", "--version"])
    out.append(item("node", "AVAILABLE" if rc == 0 else "MISSING", o.strip(), True, "install Node >= 20"))
    npx_ok = shutil.which("npx") is not None
    out.append(item("npx", "AVAILABLE" if npx_ok else "MISSING", shutil.which("npx") or "not found", True, "comes with node"))
    if npx_ok:
        rc, o = run(["npx", "--no-install", "tsx", "--version"], cwd=REPO)
        out.append(item("tsx (TypeScript runner)", "AVAILABLE" if rc == 0 else "MISSING", o.strip().splitlines()[0] if rc == 0 else "run: npm ci", True, "npm ci"))
        rc, o = run(["npx", "--no-install", "tsc", "--version"], cwd=REPO)
        out.append(item("typescript", "AVAILABLE" if rc == 0 else "MISSING", o.strip(), True, "npm ci"))
        rc, o = run(["node", "-e", "const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();console.log('chromium '+b.version());await b.close()})().catch(e=>{console.error(e.message);process.exit(1)})"], timeout=90, cwd=REPO)
        out.append(item("Chromium via Playwright (renderer)", "AVAILABLE" if rc == 0 else "MISSING", o.strip().splitlines()[-1] if o.strip() else "no output", True, "npm ci && npx playwright install chromium"))
    out.append(item("python", "AVAILABLE", sys.version.split()[0], True))
    for mod, req, why in (("numpy", True, "alignment, QA"), ("scipy", True, "alignment (DTW)"), ("PIL", True, "contact sheets, previews, thumbnails"), ("pytest", False, "the test suite")):
        try:
            m = __import__(mod)
            out.append(item(f"python:{mod}", "AVAILABLE", getattr(m, "__version__", "ok"), req))
        except Exception as e:  # noqa: BLE001
            out.append(item(f"python:{mod}", "MISSING", str(e), req, f"pip install -r requirements.txt  ({why})"))
    fonts = os.path.join(REPO, "library", "fonts")
    out.append(item("fonts", "AVAILABLE" if os.path.isdir(fonts) and any(f.endswith((".otf", ".ttf")) for _, _, fs in os.walk(fonts) for f in fs) else "MISSING", fonts, False, "library/fonts must hold the font files the style tokens name (the renderer never falls back silently)"))
    du = shutil.disk_usage(project or REPO)
    out.append(item("disk space", "AVAILABLE" if du.free > 2 * 1024**3 else "MISSING", f"{du.free / 1024**3:.1f} GB free", False, "a 8-minute 1080p60 render plus frames needs ~2 GB"))
    # services: keys are only checked for presence (never printed), calls are not made unless --net
    for name, env, what in (("ElevenLabs voice (live)", "ELEVENLABS_API_KEY", "paid narration (--stack elevenlabs)"), ("Higgsfield (credits)", "HIGGSFIELD_API_KEY", "paid image/video generation; in Claude sessions it is reached through the Higgsfield MCP tools instead")):
        has = bool(os.environ.get(env))
        out.append(item(name, "UNTESTED", f"{env} is {'set' if has else 'not set'}; this adapter has not been exercised against the live service in this environment", False, f"set {env} and run a one-line smoke call; {what}"))
    out.append(item("YouTube upload / Studio", "UNTESTED", "no upload step exists in this system: it produces youtube.md + files; publishing is manual or through your own tooling", False, ""))
    if net:
        for name, url in (("network: api.elevenlabs.io", "https://api.elevenlabs.io/v1/models"), ("network: higgsfield", "https://higgsfield.ai"), ("network: youtube", "https://www.youtube.com"), ("network: npm registry", "https://registry.npmjs.org/zod")):
            try:
                urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=8)
                out.append(item(name, "AVAILABLE", "reachable", False))
            except urllib.error.HTTPError as e:
                out.append(item(name, "AVAILABLE" if e.code < 500 and e.code not in (403, 405, 407) else "BLOCKED", f"HTTP {e.code}", False))
            except Exception as e:  # noqa: BLE001
                out.append(item(name, "BLOCKED", f"{type(e).__name__}: {str(e)[:80]} (the network allow-list may refuse this host; no other route is tried)", False))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--json")
    ap.add_argument("--net", action="store_true")
    a = ap.parse_args()
    res = check_all(a.project, a.net)
    w = max(len(r["name"]) for r in res)
    for r in res:
        print(f"{r['status']:9} {r['name']:<{w}}  {r['detail']}" + (f"   -> {r['howToFix']}" if r["status"] in ("MISSING",) and r["howToFix"] else ""))
    bad = [r for r in res if r["required"] and r["status"] != "AVAILABLE"]
    summary = {"required_missing": [r["name"] for r in bad], "untested": [r["name"] for r in res if r["status"] == "UNTESTED"], "blocked": [r["name"] for r in res if r["status"] == "BLOCKED"]}
    print(("\nREADY: everything required is available" if not bad else "\nNOT READY: " + ", ".join(summary["required_missing"])) + (f"  (untested: {len(summary['untested'])}, blocked: {len(summary['blocked'])})" if summary["untested"] or summary["blocked"] else ""))
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump({"items": res, "summary": summary}, open(a.json, "w"), indent=2)
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
