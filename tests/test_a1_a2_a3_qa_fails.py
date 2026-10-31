"""Acceptance 1-3: the QA must fail (or block) loudly, and say why. Each case runs the real qa_media.py on the real rendered smoke videos."""
import json, pathlib, shutil
import pytest
from conftest import ROOT, checks, detail, py, qa, run, tamper


# ───────── A1: a bad ffmpeg diagnostic can never become a pass ─────────
@pytest.mark.parametrize("fault,expect", [
    ("bad_filter", "No such filter|nosuchfilter|Error"),
    ("bad_audio_filter", "No such filter|nosuchaudiofilter|Error"),
    ("drop_metadata", "covers|metadata|analysed"),
    ("selfcheck_fail", "self-check"),
])
def test_a1_broken_instrument_is_never_a_pass(smoke, fault, expect):
    rc, rep, p = qa(smoke, "long", env={"QA_FAULT": fault})
    assert rc in (1, 3), f"exit {rc}: a broken instrument must not exit 0\n{p.stdout[-800:]}"
    assert rep["overall"] in ("FAILED", "BLOCKED")
    bad = [c for c in rep["checks"] if c["status"] in ("blocked", "fail")]
    assert bad, "no check reports the problem"
    import re
    assert any(re.search(expect, detail(c), re.I) for c in bad), f"no check names the cause ({expect}); got: {[detail(c)[:100] for c in bad]}"
    assert not any(c["status"] == "pass" and c["id"] in ("black", "freeze", "silence", "loudness") and fault in ("bad_filter", "drop_metadata") and c["id"] in ("black", "freeze") for c in rep["checks"]), "a gate that needed the broken pass reported PASS"


def test_a1_ffmpeg_missing_is_blocked_not_passed(smoke, tmp_path):
    # a PATH without ffmpeg/ffprobe: the QA cannot look at anything and must say so
    empty = tmp_path / "bin"
    empty.mkdir()
    import sys, os
    env = {"PATH": str(empty)}
    P = pathlib.Path(smoke)
    p = run([sys.executable, ROOT / "tools/qa_media.py", P / "out/full-video.mp4", "--plan", P / "render/plan-long.json", "--allow", P / "qa/allow-long.json", "--out", tmp_path / "r.json"], env={**env})
    assert p.returncode in (1, 3), p.stdout + p.stderr
    text = p.stdout + p.stderr
    assert "ffprobe" in text or "ffmpeg" in text, "the message must name the missing tool"
    assert "PASSED" not in text.split("overall")[-1]


def test_a1_corrupt_file_is_not_a_pass(smoke, tmp_path):
    P = pathlib.Path(smoke)
    data = (P / "out/full-video.mp4").read_bytes()
    bad = tmp_path / "truncated.mp4"
    bad.write_bytes(data[: len(data) // 3])
    rc, rep, p = qa(smoke, "long", video=bad, out=tmp_path / "r.json")
    assert rc in (1, 3)
    assert rep["overall"] in ("FAILED", "BLOCKED")


def test_a1_baseline_passes(smoke):
    rc, rep, p = qa(smoke, "long")
    assert rc == 0 and rep["overall"] == "PASSED", p.stdout[-1500:]
    rc, rep, p = qa(smoke, "S01")
    assert rc == 0 and rep["overall"] == "PASSED", p.stdout[-1500:]


# ───────── A2: an accidental black tail fails ─────────
def test_a2_black_tail_on_a_file_with_declared_fade_fails(smoke, tmp_path):
    # the long declares a 0.4 s fade-out at the very end (12.3-12.7 s); black from 11.0 s is not declared
    bad = tamper(smoke / "out/full-video.mp4", tmp_path / "blacktail.mp4", vf="drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,11.0)'")
    rc, rep, p = qa(smoke, "long", video=bad, out=tmp_path / "r.json")
    assert rc == 1 and rep["overall"] == "FAILED"
    c = checks(rep, "black", "fail")
    assert c, [ (x["id"], x["status"]) for x in rep["checks"]]
    assert "11." in detail(c[0]) or "12." in detail(c[0]), detail(c[0])


def test_a2_black_tail_on_a_file_without_declared_fade_fails(smoke, tmp_path):
    # the Short declares no fade at all, so it may not contain ANY black (v2 tolerated black at the end of every file)
    bad = tamper(smoke / "out/short-01.mp4", tmp_path / "blacktail-short.mp4", vf="drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='gte(t,13.1)'")
    rc, rep, p = qa(smoke, "S01", video=bad, out=tmp_path / "r.json")
    assert rc == 1, p.stdout[-800:]
    assert checks(rep, "black", "fail"), [(x["id"], x["status"]) for x in rep["checks"]]


def test_a2_declared_fade_that_is_missing_fails(smoke, tmp_path):
    # the other direction: the plan promises a fade-in from black, the file starts bright
    bad = tamper(smoke / "out/full-video.mp4", tmp_path / "nofade.mp4", vf="select='gte(n,12)',setpts=N/(30*TB)", extra=["-af", "atrim=start=0.4,asetpts=N/SR/TB"] if False else [])
    rc, rep, p = qa(smoke, "long", video=bad, out=tmp_path / "r.json")
    assert rc in (1, 3)
    assert rep["overall"] in ("FAILED", "BLOCKED")


# ───────── A3: unexpected silence in the narration fails; a declared pause does not ─────────
def test_a3_unexpected_silent_narration_span_fails(smoke, tmp_path):
    bad = tamper(smoke / "out/full-video.mp4", tmp_path / "muted.mp4", af="volume=enable='between(t,5.0,6.3)':volume=0")
    rc, rep, p = qa(smoke, "long", video=bad, out=tmp_path / "r.json")
    assert rc == 1 and rep["overall"] == "FAILED"
    assert checks(rep, "silence", "fail"), [(x["id"], x["status"]) for x in rep["checks"]]
    n = checks(rep, "narration", "fail")
    assert n, "the words the plan places in that span are silent: the narration check must fail"
    assert "5." in detail(n[0]) or "6." in detail(n[0])


def test_a3_declared_pause_is_authorised_and_an_extra_one_is_not(tmp_path):
    from conftest import make_project, SIZE
    P = make_project("pause")
    sc = json.loads((P / "scenes.json").read_text())
    for s in sc["scenes"]:
        if s["id"] == "s02":
            s["voice"]["pauseAfterMs"] = 1200  # a declared 1.2 s pause after s02: a silence the plan itself names
    (P / "scenes.json").write_text(json.dumps(sc, indent=2))
    p = py("pipeline.py", "run", "--project", P, "--size", "480x270", "--targets", "long", "--no-qa", timeout=900)
    assert p.returncode == 0, p.stdout[-2500:]
    plan = json.loads((P / "render/plan-long.json").read_text())
    # the recorded window is the declared 1.2 s plus the natural lead/tail silence of the two takes around it
    assert any(x.get("declaredMs") == 1200 and (x["toS"] - x["fromS"]) >= 1.2 for x in plan["silences"]), plan["silences"]
    p = py("pipeline.py", "run", "--project", P, "--size", "480x270", "--targets", "long", "--only", "qa")
    rep = json.loads((P / "qa/long.json").read_text())
    assert rep["overall"] == "PASSED", [(c["id"], c["status"], detail(c)[:160]) for c in rep["checks"] if c["status"] != "pass"]
    sil = checks(rep, "silence")[0]
    assert sil["status"] == "pass"
    # the same file with one more muted span inside speech: not authorised
    bad = tamper(P / "out/full-video.mp4", tmp_path / "extra-mute.mp4", af="volume=enable='between(t,2.0,3.2)':volume=0")
    rc, rep2, p = qa(P, "long", video=bad, out=tmp_path / "r.json")
    assert rc == 1 and checks(rep2, "silence", "fail"), [(c["id"], c["status"]) for c in rep2["checks"]]
