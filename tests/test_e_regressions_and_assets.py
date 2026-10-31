"""Regressions found while writing the v3 documentation, plus the one asset path the smoke project does not exercise: a raster image
(what a generated image or a retrieved photo is) travelling manifest -> plan -> Chromium -> pixels, in both aspect ratios."""
import importlib, json, pathlib, shutil, sys
import numpy as np
import pytest
from conftest import ROOT, make_project, py, run, work_root


def test_whisper_engine_is_blocked_not_guessed(tmp_path):
    wav = tmp_path / "a.wav"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", "-ar", "24000", wav], check=True)
    p = py("align.py", "--audio", wav, "--text", "hello world", "--out", tmp_path / "al.json", "--engine", "whisper")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "BLOCKED" in p.stderr and "not implemented" in p.stderr


def test_auto_alignment_never_selects_whisper_even_when_it_is_installed(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", type(sys)("faster_whisper"))
    sys.path.insert(0, str(ROOT / "tools"))
    align = importlib.import_module("align")
    assert align.pick_engine("auto") == "dtw", "an unimplemented engine must never be what `auto` picks"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert align.pick_engine("auto") == "elevenlabs"


def test_config_fps_is_honoured_and_auto_means_30():
    P = make_project("fps60")
    cfg = json.loads((P / "config.json").read_text())
    cfg["fps"] = 60
    (P / "config.json").write_text(json.dumps(cfg))
    sc = json.loads((P / "scenes.json").read_text())
    sc.pop("fps", None)
    (P / "scenes.json").write_text(json.dumps(sc))
    p = py("pipeline.py", "run", "--project", P, "--size", "320x180", "--targets", "long", "--only", "validate,voice,assemble,align,visuals,plan,lint", timeout=900)
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-800:]
    assert json.loads((P / "render/plan-long.json").read_text())["fps"] == 60
    cfg["fps"] = "auto"
    (P / "config.json").write_text(json.dumps(cfg))
    p = py("pipeline.py", "run", "--project", P, "--size", "320x180", "--targets", "long", "--only", "plan,lint", "--force", timeout=900)
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-800:]
    assert json.loads((P / "render/plan-long.json").read_text())["fps"] == 30


def _scene_mid(plan_path, sid):
    plan = json.loads(pathlib.Path(plan_path).read_text())
    s = next(x for x in plan["scenes"] if x["id"] == sid)
    return (s["startS"] + s["endS"]) / 2


def _frame(P, target, t, out_dir):
    from PIL import Image
    r = run(["npx", "tsx", "engine/render.ts", "--project", P, "--target", target, "--dump-times", f"{t:.3f}", "--dump-dir", out_dir, "--audio", "none"], timeout=600)
    assert r.returncode == 0, r.stdout[-1200:] + r.stderr[-800:]
    pngs = sorted(pathlib.Path(out_dir).glob(f"{target}-f*.png"))
    assert pngs, r.stdout[-800:]
    return np.asarray(Image.open(pngs[-1]).convert("RGB"), dtype=float)


def test_raster_image_asset_renders_in_both_layouts(smoke, tmp_path):
    from PIL import Image, ImageDraw
    P = make_project("raster")
    shutil.rmtree(P)
    shutil.copytree(smoke, P, symlinks=True)
    img = Image.new("RGB", (1200, 800), (210, 30, 30))  # left half red, right half blue: a crop or a flip would show
    ImageDraw.Draw(img).rectangle([600, 0, 1200, 800], fill=(30, 60, 210))
    (P / "assets").mkdir(exist_ok=True)
    img.save(P / "assets/hero.png")
    (P / "assets/manifest.json").write_text(json.dumps({"assets": [{"id": "hero", "kind": "image", "file": "assets/hero.png", "route": "code", "width": 1200, "height": 800, "provenance": {"tool": "test", "prompt": "two flat colour halves"}}]}))
    sc = json.loads((P / "scenes.json").read_text())
    s2 = next(s for s in sc["scenes"] if s["id"] == "s02")
    s2["entities"].append({"id": "e_hero", "role": "subject", "assetId": "hero", "enter": {"style": "none", "durationMs": 0}})
    s2["layouts"]["landscape"]["placements"]["e_hero"] = {"x": 0.5, "y": 0.5, "w": 0.5, "z": 9}
    s2["layouts"]["portrait"]["placements"]["e_hero"] = {"x": 0.5, "y": 0.5, "w": 0.7, "z": 9}
    (P / "scenes.json").write_text(json.dumps(sc))
    p = py("pipeline.py", "run", "--project", P, "--size", "640x360", "--targets", "long,S01", "--only", "validate,visuals,plan,lint", timeout=900)
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-800:]

    land = _frame(P, "long", _scene_mid(P / "render/plan-long.json", "s02"), tmp_path / "land")
    H, W, _ = land.shape  # 360 x 640
    # the image is 0.5 W wide (320 px) and 0.5 W / 1.5 high, centred: its left half sits at x in [160, 320), its right half in [320, 480)
    left, right, outside = land[H // 2, int(W * 0.40)], land[H // 2, int(W * 0.60)], land[H // 2, int(W * 0.08)]
    assert left[0] > left[2] + 60, f"landscape: the left half of the image should be red, got {left}"
    assert right[2] > right[0] + 60, f"landscape: the right half of the image should be blue, got {right}"
    assert not (abs(outside[0] - left[0]) < 30 and abs(outside[2] - left[2]) < 30), f"landscape: outside the image is not image colour {outside}"

    port = _frame(P, "S01", _scene_mid(P / "render/plan-S01.json", "s02"), tmp_path / "port")
    H, W, _ = port.shape  # 640 x 360
    left, right = port[H // 2, int(W * 0.33)], port[H // 2, int(W * 0.67)]
    assert left[0] > left[2] + 60 and right[2] > right[0] + 60, f"portrait: red then blue expected, got {left} / {right}"
