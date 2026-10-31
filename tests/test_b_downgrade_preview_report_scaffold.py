"""The pieces around the gates: automatic fallback of a complex transition that failed the motion gate, the creative preview gate, the production
report, the project scaffold and the voice sample. Real CLIs on real renders; only the paid service is a local mock."""
import json, os, pathlib, shutil, sys
import pytest
from conftest import ROOT, checks, detail, ffprobe, make_project, py, run
from mock_elevenlabs import Mock


def jl(p):
    return json.loads(pathlib.Path(p).read_text())


# ───────── transition fallback ─────────
def fake_motion_report(path, tid, typ, status="fail", kind="anchor"):
    json.dump({"overall": "FAILED", "checks": [{"id": f"motion.{tid}.{kind}", "status": status, "detail": "the anchors drift 51.2px apart (they must stay locked)"}], "transitions": [{"id": tid, "type": typ}]}, open(path, "w"))


def test_downgrade_writes_a_recorded_override_and_make_plan_applies_it(smoke, tmp_path):
    P = make_project("downgrade-unit")
    shutil.copytree(smoke / "audio", P / "audio", dirs_exist_ok=True)
    (P / "render").mkdir(exist_ok=True)
    rep = tmp_path / "motion.json"
    fake_motion_report(rep, "s01>s02", "truthful_morph")
    p = py("downgrade.py", "--project", P, "--target", "long", "--motion", rep)
    assert p.returncode == 0 and "truthful_morph -> dissolve" in p.stdout and "anchors drift" in p.stdout, p.stdout + p.stderr
    dg = jl(P / "render/downgrades.json")["targets"]["long"]["s01>s02"]
    assert dg["type"] == "dissolve" and dg["downgradedFrom"] == "truthful_morph" and dg["check"] == "motion.s01>s02.anchor" and dg["round"] == 1
    # the plan applies it: same window, other operator, the reason on record, no stale anchors
    p = py("make_plan.py", "--project", P, "--target", "long", "--size", "640x360", "--auto-fit", "--out", P / "render/plan-long.json")
    assert p.returncode == 0, p.stdout + p.stderr
    before = jl(smoke / "render/plan-long.json")["scenes"][0]["transitionOut"]
    after = jl(P / "render/plan-long.json")["scenes"][0]["transitionOut"]
    assert after["type"] == "dissolve" and after["downgradedFrom"] == "truthful_morph" and "anchor" in after["rationale"]
    assert (after["startS"], after["endS"]) == (before["startS"], before["endS"]) and "anchorFrom" not in after
    # the other target is untouched: a Short is judged on its own render
    assert "S01" not in jl(P / "render/downgrades.json")["targets"]
    # a dissolve that fails has nothing safer: stop, do not loop
    fake_motion_report(rep, "s01>s02", "dissolve", kind="exposure")
    p = py("downgrade.py", "--project", P, "--target", "long", "--motion", rep)
    assert p.returncode == 1 and "CANNOT downgrade" in p.stderr
    # nothing failed: nothing to do
    json.dump({"overall": "PASSED", "checks": [], "transitions": []}, open(rep, "w"))
    assert py("downgrade.py", "--project", P, "--target", "long", "--motion", rep).returncode == 3
    # a blocked check is not a failure: the gate could not judge, so nothing is downgraded
    fake_motion_report(rep, "s01>s02", "truthful_morph", status="blocked")
    assert py("downgrade.py", "--project", P, "--target", "long", "--motion", rep).returncode == 3


def test_pipeline_recovers_by_downgrading_and_the_same_gates_pass_the_new_render(smoke):
    """QA_FAULT=anchor_break makes the anchor check fail for every anchored operator (the instrument is what is faulty here, the loop is real):
    the pipeline must fall back to dissolve, re-plan, re-render and re-judge with the same gates, and say so."""
    P = make_project("downgrade-pipe", fresh=True)
    shutil.rmtree(P)
    shutil.copytree(smoke, P, symlinks=True)  # finished smoke run (stamps included): only what the fallback changes may re-run
    env = {"QA_FAULT": "anchor_break"}
    p = py("pipeline.py", "run", "--project", P, "--size", "640x360", env=env, timeout=1500)
    assert p.returncode == 1, "without --auto-downgrade a failed motion gate is a FAILED run\n" + p.stdout[-1500:]
    assert "FAILED" in p.stdout and not (P / "render/downgrades.json").exists()
    p = py("pipeline.py", "run", "--project", P, "--size", "640x360", "--auto-downgrade", env=env, timeout=1500)
    assert p.returncode == 0, p.stdout[-2500:] + p.stderr[-800:]
    dg = jl(P / "render/downgrades.json")["targets"]
    assert set(dg) == {"long", "S01"} and dg["long"]["s01>s02"]["downgradedFrom"] == "truthful_morph"
    for t, f in (("long", "out/full-video.mp4"), ("S01", "out/short-01.mp4")):
        plan = jl(P / f"render/plan-{t}.json")
        assert plan["scenes"][0]["transitionOut"]["type"] == "dissolve" and plan["scenes"][0]["transitionOut"]["downgradedFrom"] == "truthful_morph"
        rep = jl(P / f"qa/motion-{t}.json")
        assert rep["overall"] == "PASSED" and not checks(rep, "motion.s01>s02.anchor"), "a dissolve has no anchors to break; the pixel gates judged the new render"
        assert jl(P / f"qa/{t}.json")["overall"] == "PASSED"
        assert ffprobe(P / f)["duration"] == pytest.approx(plan["durationS"], abs=0.05)
    last = jl(P / "render/pipeline-last.json")
    assert any("downgraded" in n for n in last["notes"]) and last["qa"] == {"long": "PASSED", "S01": "PASSED"}
    # and the production report says what happened, in the gate's own words
    assert py("report.py", "--project", P).returncode == 0
    md = (P / "review/production-report.md").read_text()
    assert "downgraded from truthful_morph" in md and "anchor" in md


# ───────── creative preview gate ─────────
def test_preview_gate_blocks_the_pipeline_until_the_creator_approves_the_current_look(tmp_path):
    P = make_project("preview-gate")
    cfg = jl(P / "config.json")
    cfg["previewGate"] = "required"
    (P / "config.json").write_text(json.dumps(cfg))
    run_validate = lambda: py("pipeline.py", "run", "--project", P, "--only", "validate")  # noqa: E731
    p = run_validate()
    assert p.returncode == 5 and "PREVIEW GATE" in p.stderr and "preview.py make" in p.stderr
    assert py("preview.py", "approve", "--project", P).returncode == 1, "nothing to approve yet"
    p = py("preview.py", "make", "--project", P, timeout=900)
    assert p.returncode == 0, p.stdout + p.stderr
    pj = jl(P / "review/preview/preview.json")
    for k in ("hero-landscape", "hero-portrait", "technical-landscape", "technical-portrait", "transition-landscape", "transition-portrait", "voice-sample", "contact"):
        assert (P / pj["files"][k]).stat().st_size > 1000, k
    from PIL import Image
    assert Image.open(P / pj["files"]["hero-landscape"]).size == (640, 360) and Image.open(P / pj["files"]["hero-portrait"]).size == (360, 640)
    for k, wh in (("transition-landscape", (640, 360)), ("transition-portrait", (360, 640))):
        v = ffprobe(P / pj["files"][k])["video"]
        assert (v["width"], v["height"]) == wh
    assert pj["voiceSample"]["status"] == "MADE" and "draft" in pj["voiceSample"]["meaning"] and "estimated" in pj["timing"]
    assert py("preview.py", "status", "--project", P).returncode == 1  # made, not approved
    assert run_validate().returncode == 5
    assert py("preview.py", "approve", "--project", P, "--note", "looks right").returncode == 0
    assert py("preview.py", "status", "--project", P).returncode == 0
    assert run_validate().returncode == 0
    # correcting narration or a layout later does not need a new approval ...
    sc = jl(P / "scenes.json")
    sc["scenes"][0]["narration"] = sc["scenes"][0]["narration"] + " Really."
    (P / "scenes.json").write_text(json.dumps(sc))
    assert run_validate().returncode == 0
    # ... changing the look does: the approval was for a different video
    tok = jl(P / "style-tokens.json")
    tok["palette"]["accent"] = "#ff0066"
    (P / "style-tokens.json").write_text(json.dumps(tok))
    p = run_validate()
    assert p.returncode == 5 and "changed after the creator approved" in p.stderr
    assert py("preview.py", "approve", "--project", P).returncode == 1, "the old preview no longer shows this look"


def test_preview_is_honest_when_the_voice_sample_cannot_be_paid_for(tmp_path):
    P = make_project("preview-voice")
    p = py("preview.py", "make", "--project", P, "--voice-stack", "elevenlabs", "--voice-id", "v1", timeout=900, env={"ELEVENLABS_API_KEY": "x"})
    assert p.returncode == 0, p.stdout + p.stderr
    v = jl(P / "review/preview/preview.json")["voiceSample"]
    assert v["status"] == "REFUSED" and not (P / "review/preview/voice-sample.wav").exists(), "an unapproved paid sample must not be made"
    assert "voice sample not made (REFUSED)" in p.stdout


def test_voice_sample_is_spend_gated_ledgered_and_not_paid_twice():
    m = Mock().start()
    try:
        P = make_project("voice-sample")
        env = {"ELEVENLABS_API_KEY": m.key}
        args = ["--project", P, "--stack", "elevenlabs", "--base-url", m.url, "--voice-id", "voiceA", "--sample", "Hello there, this is a short sample."]
        assert py("voice.py", *args, env=env).returncode == 4 and m.count == 0
        assert py("ledger.py", "--project", P, "approve", "--service", "elevenlabs", "--ceiling", 200, "--unit", "chars").returncode == 0
        assert py("voice.py", *args, env=env).returncode == 0 and m.count == 1
        assert py("voice.py", *args, env=env).returncode == 0 and m.count == 1, "the same sample is reused, not bought again"
        assert ffprobe(P / "review/preview/voice-sample.wav")["duration"] > 0.5
        sys.path.insert(0, str(ROOT / "tools"))
        from ledger import Ledger
        L = Ledger(str(P))
        assert [e["status"] for e in L.entries()] == ["intent", "submitted", "done"] and L.status()[0]["spent"] == pytest.approx(len("Hello there, this is a short sample."))
    finally:
        m.stop()


# ───────── production report ─────────
def test_production_report_is_built_from_the_runs_own_files(smoke):
    p = py("report.py", "--project", smoke)
    assert p.returncode == 0, p.stdout + p.stderr
    md = (smoke / "review/production-report.md").read_text()
    js = jl(smoke / "review/production-report.json")
    assert js["purpose"] == "smoke" and "not a production video" in md
    for t, f in (("long", "out/full-video.mp4"), ("S01", "out/short-01.mp4")):
        r = js["targets"][t]
        assert r["media"] == "PASSED" and r["motion"] == "PASSED" and r["file"] == f
        from common import sha256_file
        assert r["sha256"] == sha256_file(str(smoke / f)), "the report's hash is the delivered file's"
    assert "no paid service was approved or used" in md and "FALLBACK" in md and "robotic" in md
    assert "PASSED never means the video is good" in md
    # an unfinished project is reported as not run, never as fine
    P = make_project("report-empty")
    for d in ("qa", "out", "render"):
        shutil.rmtree(P / d, ignore_errors=True)
    py("report.py", "--project", P)
    js = jl(P / "review/production-report.json")
    assert all(v["media"] == "NOT RUN" and v["file"] is None for v in js["targets"].values()) or js["targets"] == {}


# ───────── scaffold ─────────
def test_new_project_scaffolds_and_the_pipeline_names_what_is_missing(tmp_path):
    p = py("new_project.py", "--idea", "How big is a nucleus, really?", "--slug", "zz-new", "--dir", tmp_path)
    assert p.returncode == 0, p.stderr
    P = tmp_path / "zz-new"
    cfg = jl(P / "config.json")
    assert cfg["previewGate"] == "required" and cfg["purpose"] == "production" and cfg["maxPaidSpend"]["higgsfieldCredits"] == 15 and cfg["targetDurationMin"][0] >= 5
    assert jl(P / "state.json")["spendGate"]["status"] == "not_reached" and (P / "style-tokens.json").exists()
    assert py("new_project.py", "--idea", "x again", "--slug", "zz-new", "--dir", tmp_path).returncode == 1, "an existing project is never overwritten"
    q = py("pipeline.py", "run", "--project", P)
    assert q.returncode == 2 and "scenes.json is missing" in q.stderr
    t = py("new_project.py", "--idea", "A short test about atoms", "--slug", "zz-test", "--dir", tmp_path, "--purpose", "test_clip")
    assert t.returncode == 0 and jl(tmp_path / "zz-test/config.json")["targetDurationMin"] == [0.75, 1.25]


# ───────── thumbnails ─────────
def test_thumbnails_are_frames_of_the_video_with_a_checked_headline(smoke, tmp_path):
    P = make_project("thumbs")
    shutil.rmtree(P)
    shutil.copytree(smoke, P, symlinks=True)
    p = py("thumbnail.py", "--project", P, "--text", "Wide or Tall", timeout=600)
    assert p.returncode == 0, p.stdout + p.stderr
    from PIL import Image
    rep = jl(P / "review/thumbnails.json")
    assert len(rep["thumbnails"]) == 3 and all(t["ok"] for t in rep["thumbnails"])
    for t in rep["thumbnails"]:
        f = P / t["file"]
        assert Image.open(f).size == (1280, 720) and f.stat().st_size < 2 * 1024 * 1024
    # the promise has to be short: four words are refused, nothing is written for them
    q = py("thumbnail.py", "--project", P, "--text", "this is far too long")
    assert q.returncode == 2 and "1-3 words" in q.stderr
    # the pipeline writes the production report itself (a run that stopped early still gets one)
    assert (smoke / "review/production-report.md").exists()
