"""Regressions found while writing the v3 documentation, plus the one asset path the smoke project does not exercise: a raster image
(what a generated image or a retrieved photo is) travelling manifest -> plan -> Chromium -> pixels, in both aspect ratios."""
import importlib, json, pathlib, shutil, sys
import numpy as np
import pytest
from conftest import ROOT, make_project, py, run, work_root


def _has_whisper():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def test_whisper_engine_fails_closed_without_speech_or_package(tmp_path):
    """No package -> BLOCKED (exit 3). With the package, audio that does not say the script must FAIL (exit 4), never pass with guessed times."""
    wav = tmp_path / "a.wav"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=1", "-ar", "24000", wav], check=True)
    p = py("align.py", "--audio", wav, "--text", "hello world", "--out", tmp_path / "al.json", "--engine", "whisper")
    if _has_whisper():
        assert p.returncode == 4, p.stdout + p.stderr
        assert "FAILED" in p.stderr and "matched" in p.stderr
    else:
        assert p.returncode == 3, p.stdout + p.stderr
        assert "BLOCKED" in p.stderr


@pytest.mark.skipif(not _has_whisper(), reason="faster-whisper not installed")
def test_whisper_engine_aligns_real_speech_to_the_script(tmp_path):
    text = "The stars are born in cold clouds of gas and dust, and the heaviest of them end as black holes."
    wav = tmp_path / "s.wav"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"flite=text='{text}':voice=slt", "-ar", "24000", wav], check=True)
    p = py("align.py", "--audio", wav, "--text", text, "--out", tmp_path / "al.json", "--engine", "whisper", timeout=900)
    if p.returncode == 3:
        pytest.skip("whisper model could not be loaded here: " + p.stderr[-300:])
    assert p.returncode == 0, p.stdout + p.stderr
    doc = json.loads((tmp_path / "al.json").read_text())
    assert doc["source"] == "whisper" and doc["coverage"] == 1.0
    ws = doc["words"]
    assert [w["w"] for w in ws] == text.split()
    assert all(b["s"] >= a["s"] for a, b in zip(ws, ws[1:])) and ws[-1]["e"] <= doc["audio"]["durationS"] + 0.05
    assert sum(1 for w in ws if w["conf"] > 0.3) >= 0.85 * len(ws), "most words must come from recognised speech, not interpolation"


def test_auto_alignment_never_selects_whisper_implicitly(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ALIGN_ENGINE", raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", type(sys)("faster_whisper"))
    sys.path.insert(0, str(ROOT / "tools"))
    align = importlib.import_module("align")
    assert align.pick_engine("auto") == "dtw", "auto must not switch engines just because a package is installed"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert align.pick_engine("auto") == "elevenlabs"
    monkeypatch.setenv("ALIGN_ENGINE", "whisper")
    assert align.pick_engine("auto") == "whisper", "an explicit project choice is honoured"


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


def _lint_fixture(tmp_path, card=None, waiver=False, spoken="So how long does it last? Mass decides."):
    import json as _j
    sc = {"scenes": [{"id": "a1", "section": "s", "beat": "payoff", "narration": spoken, "claimIds": []}]}
    sh = {"shorts": [{"id": "S01", "status": "validated", "sceneIds": ["a1"], "delta": ({"openingCard": card} if card else {})}]}
    cfg = {"targetDurationMin": [0.01, 1], "purpose": "production"}
    if waiver:
        cfg["durationFloorWaivedByCreator"] = {"reason": "the creator's brief for this one video sets the length"}
    for n, d in (("scenes", sc), ("shorts", sh), ("config", cfg), ("facts", {"claims": []})):
        (tmp_path / f"{n}.json").write_text(_j.dumps(d))
    return py("lint_script.py", "--scenes", str(tmp_path / "scenes.json"), "--facts", str(tmp_path / "facts.json"),
              "--shorts", str(tmp_path / "shorts.json"), "--config", str(tmp_path / "config.json"))


def test_lint_honours_the_creators_duration_waiver_and_judges_opening_cards(tmp_path):
    r = _lint_fixture(tmp_path)  # no waiver, no card: the 5:00 floor and the backward "so" both FAIL
    assert r.returncode == 1 and "under the 300s minimum" in r.stdout and 'opening is not independent: "so"' in r.stdout
    r = _lint_fixture(tmp_path, card="What decides how a star dies?", waiver=True)
    assert r.returncode == 0, r.stdout
    assert "5:00 floor waived by the creator" in r.stdout and 'spoken opening starts with "so"' in r.stdout and "WARN" in r.stdout
    r = _lint_fixture(tmp_path, card="So what decides it?", waiver=True)  # the card itself must stand alone
    assert r.returncode == 1 and "opening card is not independent" in r.stdout
