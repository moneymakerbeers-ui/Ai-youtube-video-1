"""Acceptance 6 and 7: transitions are checked on real rendered frames (pops, exposure, stalls, anchors), and one CLI run produces the 16:9 and the
9:16 video from the same scene data."""
import json, pathlib, shutil
import pytest
from conftest import ROOT, checks, detail, ffprobe, motion, py, run, tamper

MORPH = (1.895, 3.295)  # s01 -> s02 truthful_morph window in the long plan of examples/smoke (asserted below, so a layout change fails loudly)


def frame_of(t, fps=30):
    return int(round(t * fps))


def test_a6_morph_window_matches_the_plan(smoke):
    plan = json.loads((smoke / "render/plan-long.json").read_text())
    t = next(s["transitionOut"] for s in plan["scenes"] if s["id"] == "s01")
    assert t["type"] == "truthful_morph" and (t["startS"], t["endS"]) == MORPH


def test_a6_every_transition_is_measured_on_real_frames(smoke):
    rc, rep, p = motion(smoke, "long")
    assert rc == 0 and rep["overall"] == "PASSED", p.stdout[-1200:]
    for tr in ("s01>s02", "s03>s04"):
        for what in ("boundary", "exposure", "stall", "pop", "smooth"):
            c = checks(rep, f"motion.{tr}.{what}")
            assert c and c[0]["status"] == "pass", (tr, what, [(x["id"], x["status"]) for x in rep["checks"]])
    a = checks(rep, "motion.s01>s02.anchor")[0]
    assert a["status"] == "pass" and a["value"] >= 20, "the morph's anchors must be measured on every frame of the move"
    # the detectors proved themselves on known defects before judging the file
    assert checks(rep, "selfcheck")[0]["status"] == "pass"
    rc, rep, p = motion(smoke, "S01")
    assert rc == 0, p.stdout[-800:]


def test_a6_previews_for_human_eyes_are_written(smoke):
    prev = smoke / "render/previews"
    for t in ("long", "S01"):
        assert (prev / t / "tr-s01-s02-strip.png").stat().st_size > 5000
        assert (prev / t / "tr-s01-s02.mp4").stat().st_size > 5000
    rep = json.loads((smoke / "qa/motion-long.json").read_text())
    assert any("heuristics" in detail(c) and "eyes" in detail(c) for c in checks(rep, "motion.s01>s02.preview")), "the report must say the numbers are heuristics"


# the same real file with ONE defect injected in the middle of the morph; each must be caught, by the gate that owns it
@pytest.mark.parametrize("name,vf,expect", [
    ("pop", f"split[a][b];[b]scale=iw*1.14:ih*1.14,crop=iw/1.14:ih/1.14[z];[a][z]overlay=enable='between(n,{frame_of(2.5)},{frame_of(2.5) + 1})'", ("pop",)),
    ("flash", f"eq=brightness=0.5:enable='between(n,{frame_of(2.5)},{frame_of(2.5) + 1})'", ("exposure",)),
    ("stall", f"split[a][b];[a][b]freezeframes=first={frame_of(2.3)}:last={frame_of(2.3) + 9}:replace={frame_of(2.3) + 1}", ("stall",)),
])
def test_a6_defects_injected_into_the_real_morph_are_caught(smoke, tmp_path, name, vf, expect):
    bad = tamper(smoke / "out/full-video.mp4", tmp_path / f"{name}.mp4", vf=vf)
    rc, rep, p = motion(smoke, "long", video=bad, out=tmp_path / "m.json")
    assert rc == 1 and rep["overall"] == "FAILED", f"{name}: the defect passed\n{p.stdout[-1500:]}"
    failing = [c["id"] for c in rep["checks"] if c["status"] == "fail"]
    assert any(c.startswith("motion.s01>s02.") and c.split(".")[-1] in expect for c in failing), f"{name}: expected one of {expect}, failing: {failing}"
    # the untouched dissolve is still judged clean: the gate points at the transition that is broken
    assert all(not c.startswith("motion.s03>s04.") for c in failing), failing


@pytest.mark.parametrize("name,moved", [("pair_jumps", ("aOut", "bOut")), ("one_side_drifts", ("bOut",))])
def test_a6_a_renderer_that_loses_an_anchor_is_caught_from_the_trace(smoke, tmp_path, name, moved):
    """The anchor check reads the rectangles the renderer reports for both anchored entities on every frame of the morph: a one-frame sideways
    jump of the locked pair leaves the straight path between the rest positions; a single side drifting breaks the lock."""
    tr = json.loads((smoke / "render/trace-long.json").read_text())
    frames = [f for f in tr["transitionFrames"] if f["used"] == "truthful_morph"]
    assert len(frames) >= 20
    mid = frames[len(frames) // 2]
    for k in moved:
        mid[k]["cx"] += 0.2 * mid[k]["w"]
    bad_trace = tmp_path / "trace.json"
    bad_trace.write_text(json.dumps(tr))
    out = tmp_path / "m.json"
    p = py("qa_motion.py", smoke / "out/full-video.mp4", "--plan", smoke / "render/plan-long.json", "--trace", bad_trace, "--thresholds", ROOT / "library/thresholds.json", "--out", out, "--no-previews")
    rep = json.loads(out.read_text())
    bad = checks(rep, "motion.s01>s02.anchor", "fail")
    assert p.returncode == 1 and bad, [(c["id"], c["status"]) for c in rep["checks"]]
    assert "px" in detail(bad[0]), "the finding must say how far the anchor strayed"
    # the other transition and every pixel check are untouched: the trace alone made the verdict
    assert not [c for c in rep["checks"] if c["status"] == "fail" and not c["id"].endswith(".anchor")]


def test_a6_an_abrupt_audio_step_at_the_window_edge_is_warned_but_the_voices_own_onsets_are_not(smoke, tmp_path):
    nar = smoke / "audio/narration.wav"
    cmd = [smoke / "out/full-video.mp4", "--plan", smoke / "render/plan-long.json", "--trace", smoke / "render/trace-long.json", "--narration", nar, "--no-previews"]
    p = py("qa_motion.py", *cmd, "--out", tmp_path / "ok.json")
    rep = json.loads((tmp_path / "ok.json").read_text())
    assert p.returncode == 0 and not [c for c in rep["checks"] if c["status"] == "warn"], "speech onsets inside the window are the voice's own, not a defect"


def test_a6_audio_edge_instrument_on_known_signals():
    """audio_edges on signals with known truth: a gain step the mix added, the same step present in the narration stem (the voice's own), a click."""
    import numpy as np
    import qa_motion as Q
    th = json.loads(json.dumps(Q.DEFAULTS))
    sr, rng = 16000, np.random.default_rng(3)
    base = (0.02 * rng.standard_normal(sr * 4)).astype("float32")
    step = base.copy(); step[int(2.0 * sr):] *= 10  # +20 dB at t = 2.0 s
    assert [k for _, k, _ in Q.audio_edges(step, sr, [2.0], [], th)] == ["step"], "an unexplained 20 dB step at the window edge must be reported"
    assert Q.audio_edges(step, sr, [2.0], [], th, ref=step) == [], "the narration stem has the same step: it is the voice's, not the transition's"
    assert Q.audio_edges(step, sr, [2.0], [{"s": 2.0, "e": 2.4}], th) == [], "a word onset is the voice's"
    assert Q.audio_edges(base, sr, [2.0], [], th) == [], "steady audio is fine"
    click = base.copy(); click[int(2.0 * sr)] = 0.9  # one-sample click in a -34 dB bed
    assert "click" in [k for _, k, _ in Q.audio_edges(click, sr, [2.0], [], th)]
    assert not [1 for _, k, _ in Q.audio_edges(click, sr, [2.0], [], th, ref=base) if k == "step"]


def test_a6_detectors_pass_their_own_self_check_and_a_failed_self_check_blocks_everything(smoke):
    p = py("qa_motion.py", "--selfcheck")
    assert p.returncode == 0, p.stdout[-1000:]
    for kind in ("good", "pop", "flash", "stall"):
        assert f"  {kind} " in p.stdout, p.stdout
    assert "SELFCHECK PASSED" in p.stdout
    # when the instruments cannot classify the known defects, no transition is declared fine: BLOCKED, never green
    q = py("qa_motion.py", smoke / "out/full-video.mp4", "--plan", smoke / "render/plan-long.json", "--trace", smoke / "render/trace-long.json", "--no-previews", env={"QA_FAULT": "selfcheck_fail"})
    assert q.returncode == 3 and "BLOCKED" in q.stdout, q.stdout[-800:]
    assert "PASSED" not in q.stdout.splitlines()[-1]


# ───────── A7: one working CLI, two aspect ratios, one scene file ─────────
def test_a7_cli_produced_both_videos_from_the_same_scene_data(smoke):
    L, S = ffprobe(smoke / "out/full-video.mp4"), ffprobe(smoke / "out/short-01.mp4")
    assert (L["video"]["width"], L["video"]["height"]) == (640, 360)
    assert (S["video"]["width"], S["video"]["height"]) == (360, 640)
    for v in (L, S):
        assert v["video"]["codec_name"] == "h264" and v["video"]["pix_fmt"] == "yuv420p" and v["audio"]["codec_name"] == "aac"
        assert v["video"]["color_space"] == "bt709" and v["video"]["color_range"] == "tv"
    pl, ps = (json.loads((smoke / f"render/plan-{t}.json").read_text()) for t in ("long", "S01"))
    assert L["duration"] == pytest.approx(pl["durationS"], abs=0.05) and S["duration"] == pytest.approx(ps["durationS"], abs=0.05)
    # shared scene data: every scene of the Short is a scene of the long video, with the same entities, placed by its own portrait layout
    scenes = {s["id"]: s for s in json.loads((smoke / "scenes.json").read_text())["scenes"]}
    ents_long = {s["id"]: sorted(e["id"] for e in s["entities"]) for s in pl["scenes"]}
    ents_short = {s["id"]: sorted(e["id"] for e in s["entities"]) for s in ps["scenes"]}
    assert pl["layout"] == "landscape" and ps["layout"] == "portrait"
    assert set(ents_short) <= set(ents_long)
    for sid, ents in ents_short.items():
        assert ents == ents_long[sid] == sorted(e["id"] for e in scenes[sid]["entities"])
    # recomposed, not cropped: the portrait layout places the same entities elsewhere
    moved = sum(1 for sid in ents_short for e in scenes[sid]["layouts"]["portrait"]["placements"] if scenes[sid]["layouts"]["portrait"]["placements"][e] != scenes[sid]["layouts"]["landscape"]["placements"][e])
    assert moved >= 3
    # both came out of one pipeline run
    last = json.loads((smoke / "render/pipeline-last.json").read_text())
    names = {r["step"] for r in last["results"] if r["status"] in ("ok", "skipped")}
    assert {"render:long", "render:S01", "captions:long", "captions:S01", "qa:long", "qa:S01"} <= names
    assert (smoke / "out/captions.srt").stat().st_size > 50 and (smoke / "out/short-01.srt").stat().st_size > 50


def test_a7_both_files_play_through_without_decode_errors(smoke):
    for f in ("out/full-video.mp4", "out/short-01.mp4"):
        p = run(["ffmpeg", "-v", "error", "-nostdin", "-i", smoke / f, "-f", "null", "-"])
        assert p.returncode == 0 and p.stderr.strip() == "", p.stderr[:500]
        n = int(run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", smoke / f]).stdout.strip())
        assert n == round(ffprobe(smoke / f)["duration"] * 30)


def test_a7_pipeline_is_resumable_and_does_not_redo_finished_steps(smoke):
    p = py("pipeline.py", "run", "--project", smoke, "--size", "640x360")
    assert p.returncode == 0
    lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith(("ok", "skip"))]
    assert any("skip   render:long" in ln for ln in lines) and any("skip   voice" in ln for ln in lines), p.stdout[-1500:]
    assert not any(ln.strip().startswith("ok     render") or ln.strip().startswith("ok     voice") for ln in lines), "nothing changed, nothing may be redone"
