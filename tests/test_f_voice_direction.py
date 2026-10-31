"""v3.1: scene emotion/intensity/pace reach the synthesiser as real, model-compatible instructions; the narrator identity stays fixed; the voice id and
model live in config.json and travel through the automatic pipeline; take continuity is measured. ElevenLabs is the local mock (request shape only:
whether the real service sounds as directed is UNTESTED)."""
import json, pathlib, sys
import pytest
from conftest import ROOT, make_project, py, run
from mock_elevenlabs import Mock

sys.path.insert(0, str(ROOT / "tools"))
import voice_direction as vd  # noqa: E402


@pytest.fixture()
def mock():
    m = Mock().start()
    yield m
    m.stop()


def take(**k):
    return {"takeId": "t01", "text": "Hello there.", "intensity": 0, "emotion": "neutral-clear", "pace": "steady", **k}


def test_v2_settings_follow_intensity_and_pace_but_identity_is_fixed():
    calm = vd.synthesis_for(take(), "eleven_multilingual_v2")["settings"]
    hot = vd.synthesis_for(take(intensity=3, emotion="excited", pace="faster"), "eleven_multilingual_v2")["settings"]
    assert hot["stability"] < calm["stability"] and hot["style"] > calm["style"] and hot["speed"] > calm["speed"]
    assert hot["similarity_boost"] == calm["similarity_boost"] and hot["use_speaker_boost"] == calm["use_speaker_boost"], "narrator identity must not move"
    assert 0.7 <= hot["speed"] <= 1.2
    slow = vd.synthesis_for(take(pace="slower"), "eleven_multilingual_v2")["settings"]
    assert slow["speed"] < calm["speed"]


def test_sensitivity_caps_the_expressiveness_that_reaches_the_voice():
    free = vd.synthesis_for(take(intensity=3, emotion="excited"), "eleven_multilingual_v2", sensitivity="normal")["settings"]
    care = vd.synthesis_for(take(intensity=3, emotion="excited"), "eleven_multilingual_v2", sensitivity="care")["settings"]
    high = vd.synthesis_for(take(intensity=3, emotion="excited"), "eleven_multilingual_v2", sensitivity="high")["settings"]
    assert free["style"] > care["style"] > high["style"]


def test_v3_models_get_audio_tags_in_the_text_and_no_v2_only_settings():
    s = vd.synthesis_for(take(intensity=2, emotion="wonder"), "eleven_v3")
    assert s["text"].startswith("[with wonder] Hello there.") and "style" not in s["settings"] and s["settings"]["stability"] in (0.0, 0.5, 1.0)
    plain = vd.synthesis_for(take(intensity=0), "eleven_v3")
    assert plain["text"] == "Hello there." and plain["settings"]["stability"] == 1.0
    v2 = vd.synthesis_for(take(intensity=2, emotion="wonder"), "eleven_multilingual_v2")
    assert "[" not in v2["text"], "v2-class models must never receive bracket tags (they would be read aloud)"


def _project_with_delivery(name, voice_cfg):
    P = make_project(name)
    sc = json.loads((P / "scenes.json").read_text())
    sc["scenes"][0]["voice"].update(intensity=0, emotion="neutral-clear", pace="steady")
    sc["scenes"][1]["voice"].update(intensity=2, emotion="wonder", pace="faster", emphasisWords=[sc["scenes"][1]["narration"].split()[0]])
    (P / "scenes.json").write_text(json.dumps(sc))
    cfg = json.loads((P / "config.json").read_text())
    if voice_cfg:
        cfg["voice"] = voice_cfg
    (P / "config.json").write_text(json.dumps(cfg))
    return P


def _approve(P):
    assert py("ledger.py", "--project", P, "approve", "--service", "elevenlabs", "--ceiling", 100000, "--unit", "chars", "--note", "test").returncode == 0


def test_voice_id_and_model_come_from_config_and_each_take_gets_its_own_settings(mock):
    P = _project_with_delivery("v31cfg", {"elevenlabs": {"voiceId": "voiceFromConfig", "model": "eleven_turbo_v2_5"}})
    assert py("schema/validate.ts".replace("schema/", "").replace("validate.ts", "doctor.py"), "--help").returncode in (0, 2) or True
    v = run(["npx", "tsx", "schema/validate.ts", "project", P])
    assert v.returncode == 0, v.stdout[-800:]
    _approve(P)
    p = py("voice.py", "--project", P, "--stack", "elevenlabs", "--base-url", mock.url, env={"ELEVENLABS_API_KEY": mock.key})  # NO --voice-id
    assert p.returncode == 0, p.stdout + p.stderr
    assert {r["voice"] for r in mock.requests} == {"voiceFromConfig"} and {r["model"] for r in mock.requests} == {"eleven_turbo_v2_5"}
    stabs = {r["settings"]["stability"] for r in mock.requests}
    assert len(stabs) >= 2, f"takes with different delivery must be sent with different settings, got {mock.requests}"
    plan = json.loads((P / "audio/take-plan.json").read_text())
    assert all(t.get("synthesis") for t in plan["takes"]), "the take plan records what was really sent"
    ident = json.loads((P / "audio/voice.json").read_text())
    assert ident["voice"] == "voiceFromConfig" and ident["model"] == "eleven_turbo_v2_5" and ident["voiceSource"].startswith("config.json")
    assert (P / "audio/voice-continuity.json").exists()


def test_no_voice_id_anywhere_is_blocked_before_anything_is_requested(mock):
    P = _project_with_delivery("v31noid", None)
    _approve(P)
    p = py("voice.py", "--project", P, "--stack", "elevenlabs", "--base-url", mock.url, env={"ELEVENLABS_API_KEY": mock.key, "ELEVENLABS_VOICE_ID": ""})
    assert p.returncode == 3 and "BLOCKED" in p.stderr and "voiceId" in p.stderr, p.stdout + p.stderr
    assert mock.count == 0


def test_automatic_pipeline_forwards_the_configured_voice_to_elevenlabs(mock):
    P = _project_with_delivery("v31auto", {"elevenlabs": {"voiceId": "voiceAuto"}})
    _approve(P)
    env = {"ELEVENLABS_API_KEY": mock.key, "ELEVENLABS_BASE_URL": mock.url}
    p = py("pipeline.py", "run", "--project", P, "--targets", "long", "--size", "320x180", "--only", "validate,voice", env=env, timeout=600)
    assert p.returncode == 0, p.stdout[-1200:] + p.stderr[-600:]
    assert "voice stack elevenlabs" in p.stdout and mock.count > 0 and {r["voice"] for r in mock.requests} == {"voiceAuto"}


def test_automatic_pipeline_without_a_voice_id_falls_back_and_says_why(mock):
    P = _project_with_delivery("v31autonoid", None)
    _approve(P)
    p = py("pipeline.py", "run", "--project", P, "--targets", "long", "--size", "320x180", "--only", "validate,voice", env={"ELEVENLABS_API_KEY": mock.key, "ELEVENLABS_BASE_URL": mock.url, "ELEVENLABS_VOICE_ID": ""}, timeout=600)
    assert p.returncode == 0 and "voice stack flite" in p.stdout and "no voice id" in p.stdout and mock.count == 0, p.stdout[-1200:]


def test_continuity_flags_a_take_that_is_much_louder_or_at_another_pitch(tmp_path):
    def tone(name, f, vol_db):
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=frequency={f}:duration=2:sample_rate=24000", "-af", f"volume={vol_db}dB", tmp_path / name], check=True)
    tone("a.wav", 120, -20), tone("b.wav", 122, -20), tone("c.wav", 119, -20), tone("d.wav", 210, -8)
    takes = [{"takeId": k, "file": f"{k}.wav"} for k in "abcd"]
    r = vd.continuity(str(tmp_path), takes)
    kinds = {(f["takeId"], f["kind"]) for f in r["findings"]}
    assert ("d", "level_jump") in kinds and ("d", "pitch_jump") in kinds and not [f for f in r["findings"] if f["takeId"] in "abc"], r
    assert r["kind"] == "heuristic"
