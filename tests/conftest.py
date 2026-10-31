"""Shared fixtures. The `smoke` fixture runs the real CLI (tools/pipeline.py) on examples/smoke once per session: narration, alignment,
a 16:9 render and a 9:16 render from the same scenes.json, and every QA gate. Nothing here is mocked except the paid services."""
import json, os, shutil, subprocess, sys, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT / "tests"))
SIZE = "640x360"


def run(cmd, env=None, cwd=ROOT, timeout=900, check=False):
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})
    if check and p.returncode:
        raise AssertionError(f"{cmd} exited {p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


def py(script, *args, **kw):
    return run([sys.executable, TOOLS / script, *args], **kw)


def ffprobe(path):
    p = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], check=True)
    d = json.loads(p.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return {"video": v, "audio": a, "duration": float(d["format"]["duration"])}


def work_root():
    d = ROOT / "tests" / ".work"
    d.mkdir(exist_ok=True)
    return d


def make_project(name, src="examples/smoke", fresh=True):
    """A scratch copy of an example project with the shared library linked in (never copied into the deliverable)."""
    dst = work_root() / name
    if fresh and dst.exists():
        shutil.rmtree(dst)
    if not dst.exists():
        shutil.copytree(ROOT / src, dst)
        os.symlink(ROOT / "library", dst / "library")
    return dst


@pytest.fixture(scope="session")
def smoke():
    """examples/smoke after a complete run of the real pipeline (reused between sessions unless FRESH=1; every step is stamp-cached)."""
    dst = make_project("smoke", fresh=bool(os.environ.get("FRESH")))
    p = py("pipeline.py", "run", "--project", dst, "--size", SIZE, timeout=1500)
    assert p.returncode == 0, f"pipeline exited {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-1500:]}"
    return dst


def qa(project, target, video=None, env=None, extra=(), out=None, trace=True):
    """qa_media.py exactly as the pipeline calls it (optionally on a different video). Returns (returncode, report dict, process)."""
    P = pathlib.Path(project)
    video = video or P / ("out/full-video.mp4" if target == "long" else f"out/short-{target[1:].zfill(2)}.mp4")
    out = out or (P / "qa" / f"test-{target}-{pathlib.Path(video).stem}.json")
    cmd = [video, "--plan", P / f"render/plan-{target}.json", "--allow", P / f"qa/allow-{target}.json", "--tokens", P / "style-tokens.json", "--master", P / f"audio/master-{target}.wav", "--thresholds", ROOT / "library/thresholds.json", "--out", out, *extra]
    if trace:
        cmd += ["--trace", P / f"render/trace-{target}.json"]
    p = py("qa_media.py", *cmd, env=env)
    rep = json.loads(pathlib.Path(out).read_text()) if pathlib.Path(out).exists() else None
    return p.returncode, rep, p


def motion(project, target, video=None, out=None, previews=False):
    P = pathlib.Path(project)
    video = video or P / ("out/full-video.mp4" if target == "long" else f"out/short-{target[1:].zfill(2)}.mp4")
    out = out or (P / "qa" / f"test-motion-{target}-{pathlib.Path(video).stem}.json")
    cmd = [video, "--plan", P / f"render/plan-{target}.json", "--trace", P / f"render/trace-{target}.json", "--thresholds", ROOT / "library/thresholds.json", "--out", out]
    if not previews:
        cmd.append("--no-previews")
    p = py("qa_motion.py", *cmd)
    return p.returncode, (json.loads(pathlib.Path(out).read_text()) if pathlib.Path(out).exists() else None), p


def checks(rep, cid=None, status=None):
    return [c for c in rep["checks"] if (cid is None or c["id"] == cid or c["id"].startswith(cid + ".")) and (status is None or c["status"] == status)]


def detail(c):
    return str(c.get("detail") or c.get("msg") or c.get("message") or "")


def tamper(src, dst, vf=None, af=None, extra=()):
    """Write a copy of `src` with a video and/or audio filter applied (the other stream is copied)."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", src]
    if vf:
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if af else ["-c:a", "copy"]
    run([*cmd, *extra, dst], check=True)
    return dst
