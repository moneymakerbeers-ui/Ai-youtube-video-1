"""Fast regression tests for the local readiness fixes; no browser or paid API required."""
import pathlib, subprocess, sys, json
from types import SimpleNamespace
from conftest import ROOT
sys.path.insert(0, str(ROOT / "tools"))
from pipeline import Pipeline, project_asset_files
from voice_direction import synthesis_for


def test_resume_rebuilds_a_corrupted_or_changed_output(tmp_path):
    a = SimpleNamespace(project=str(tmp_path), only=None, force=False)
    pipe = Pipeline(a)
    src, out, counter = tmp_path/"src.txt", tmp_path/"output.txt", tmp_path/"count.txt"
    src.write_text("src")
    code = "from pathlib import Path; p=Path(%r); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); Path(%r).write_text('good')" % (str(counter), str(out))
    def go():
        return pipe.step("probe", [str(src)], [str(out)], [sys.executable, "-c", code])
    assert go() == 0 and counter.read_text() == "1"
    assert go() == 0 and counter.read_text() == "1", "unchanged output should be skipped"
    out.write_text("CORRUPTED")
    assert go() == 0 and counter.read_text() == "2" and out.read_text() == "good"
    src.write_text("changed input")
    assert go() == 0 and counter.read_text() == "3"


def test_asset_input_detection_tracks_changed_media(tmp_path):
    assets=tmp_path / "assets"
    assets.mkdir()
    (assets/"hero.png").write_bytes(b"version1")
    m=assets/"manifest.json"
    m.write_text(json.dumps({"assets":[{"id":"hero","file":"assets/hero.png"}]}))
    assert str(assets/"hero.png") in project_asset_files(str(tmp_path),str(m))


def test_v3_tags_are_in_actual_billing_length():
    take = {"text":"hello", "emotion":"wonder", "intensity":2, "pace":"steady"}
    v3 = synthesis_for(take,"eleven_v3")
    assert len(v3["text"]) > len(take["text"])
