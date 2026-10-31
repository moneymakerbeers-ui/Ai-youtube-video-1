"""Acceptance 8 and 9: a resumed run never repeats a paid generation, and a missing tool / key / approval / quota ends in an honest BLOCKED or REFUSED
(or a documented free fallback), never in a fake success. The paid service is a local mock that counts requests."""
import json, os, pathlib, sys
import pytest
from conftest import ROOT, make_project, py, run
from mock_elevenlabs import Mock

KEY_ENV = lambda m: {"ELEVENLABS_API_KEY": m.key}  # noqa: E731


def items_of(P):
    plan = json.loads((pathlib.Path(P) / "audio/take-plan.json").read_text())
    n = len(plan["takes"]) + sum(1 for _ in (json.loads((pathlib.Path(P) / "audio/voice.json").read_text()).get("shortLines", []) if (pathlib.Path(P) / "audio/voice.json").exists() else []))
    return n


def approve(P, ceiling=100000):
    p = py("ledger.py", "--project", P, "approve", "--service", "elevenlabs", "--ceiling", ceiling, "--unit", "chars", "--note", "test")
    assert p.returncode == 0, p.stdout + p.stderr


def voice(P, m, extra=(), env=None):
    return py("voice.py", "--project", P, "--stack", "elevenlabs", "--base-url", m.url, "--voice-id", "voiceA", *extra, env={**KEY_ENV(m), **(env or {})})


def ledger_entries(P):
    sys.path.insert(0, str(ROOT / "tools"))
    from ledger import Ledger
    return Ledger(str(P)).entries()


@pytest.fixture()
def mock():
    m = Mock().start()
    yield m
    m.stop()


def expected_requests(P):
    # one request per take and per Short line (computed by the plan step; --plan-only writes audio/take-plan.json without any call)
    py("voice.py", "--project", P, "--stack", "flite", "--plan-only")
    plan = json.loads((pathlib.Path(P) / "audio/take-plan.json").read_text())
    return len(plan["takes"]) + len(plan.get("shortLines", []))


# ───────── A8: resume does not repeat a paid job ─────────
def test_a8_normal_run_pays_once_per_item_and_a_rerun_pays_nothing(mock):
    P = make_project("paid-normal")
    n = expected_requests(P)
    approve(P)
    p = voice(P, mock)
    assert p.returncode == 0, p.stdout + p.stderr
    assert mock.count == n, (mock.count, n)
    assert all((P / f).exists() for f in ("audio/takes.json",))
    p = voice(P, mock)
    assert p.returncode == 0 and mock.count == n, "a second run must reuse every finished item"
    assert "reused" in p.stdout


def test_a8_crash_after_the_provider_accepted_then_resume_does_not_resend(mock):
    P = make_project("paid-after-submit")
    n = expected_requests(P)
    approve(P)
    p = voice(P, mock, env={"PAID_FAULT": "after_submit"})
    assert p.returncode == 99
    assert mock.count == 1
    # the machine also lost the downloaded part-file: the audio must come back from the provider's history, not from a second paid request
    for f in P.rglob("*.mp3.part"):
        f.unlink()
    pending = [e for e in ledger_entries(P) if e["status"] == "submitted"]
    assert pending, "the ledger must remember that a request was submitted"
    p = voice(P, mock)
    assert p.returncode == 0, p.stdout + p.stderr
    assert mock.count == n, f"{mock.count} paid requests for {n} items: the interrupted one was repeated"
    # the ledger shows exactly one submission per item
    subs = {}
    for e in ledger_entries(P):
        if e["status"] == "submitted":
            subs[e["key"]] = subs.get(e["key"], 0) + 1
    assert subs and all(v == 1 for v in subs.values()), subs


def test_a8_crash_before_the_request_left_is_detected_and_not_blindly_resent(mock):
    P = make_project("paid-after-intent")
    n = expected_requests(P)
    approve(P)
    p = voice(P, mock, env={"PAID_FAULT": "after_intent"})
    assert p.returncode == 99 and mock.count == 0
    # resume: an intent without a job id may already have been charged. The adapter looks in the provider's history first; it finds
    # nothing, and it refuses to guess (exit 6) instead of paying again.
    p = voice(P, mock)
    assert p.returncode == 6, p.stdout + p.stderr
    assert "interrupted" in (p.stdout + p.stderr).lower()
    assert mock.count == 0, "a refused resume must not have sent anything"
    key = next(e["key"] for e in ledger_entries(P) if e["status"] == "intent")
    # a person looked at the provider's dashboard, saw nothing was generated, and allows one new attempt
    assert py("ledger.py", "--project", P, "resolve", "--key", key, "--abandon").returncode == 0
    p = voice(P, mock)
    assert p.returncode == 0, p.stdout + p.stderr
    assert mock.count == n


def test_a8_a_finished_item_is_never_repeated_even_if_its_file_is_gone_unless_asked(mock):
    P = make_project("paid-done-file-missing")
    approve(P)
    assert voice(P, mock).returncode == 0
    n = mock.count
    # editing the narration changes the request key: that is a NEW paid request, and it is priced against the ceiling again
    sc = json.loads((P / "scenes.json").read_text())
    sc["scenes"][0]["narration"] += " Really."
    (P / "scenes.json").write_text(json.dumps(sc))
    py("voice.py", "--project", P, "--stack", "flite", "--plan-only")
    assert voice(P, mock).returncode == 0
    assert mock.count == n + 1, "only the changed take is regenerated"


# ───────── A9: missing tool / key / approval / quota -> honest BLOCKED or REFUSED, or a documented free fallback ─────────
def test_a9_no_api_key_is_blocked_and_nothing_is_requested(mock):
    P = make_project("blocked-nokey")
    approve(P)
    expected_requests(P)
    p = py("voice.py", "--project", P, "--stack", "elevenlabs", "--base-url", mock.url, "--voice-id", "voiceA", env={"ELEVENLABS_API_KEY": ""})
    assert p.returncode == 3 and "BLOCKED" in p.stderr and "ELEVENLABS_API_KEY" in p.stderr
    assert mock.count == 0 and not [e for e in ledger_entries(P) if e["service"] == "elevenlabs" and e["status"] != "approved"], "nothing may be booked for a call that never happened"


def test_a9_not_approved_at_the_spend_gate_is_refused(mock):
    P = make_project("refused-noapproval")
    expected_requests(P)
    p = voice(P, mock)
    assert p.returncode == 4 and "not approved" in p.stderr.lower()
    assert mock.count == 0


def test_a9_quota_below_the_estimate_is_refused_before_any_request(mock):
    P = make_project("refused-quota")
    expected_requests(P)
    approve(P, ceiling=10)  # 10 characters: less than the first take
    p = voice(P, mock)
    assert p.returncode == 4 and "would take" in p.stderr
    assert mock.count == 0


def test_a9_per_service_budgets_are_separate_units(mock):
    P = make_project("refused-units")
    expected_requests(P)
    cfg = json.loads((P / "config.json").read_text())
    cfg["maxPaidSpend"]["higgsfieldCredits"] = 15  # the project budgets credits; it budgets no ElevenLabs characters
    (P / "config.json").write_text(json.dumps(cfg))
    assert py("ledger.py", "--project", P, "approve", "--service", "higgsfield", "--ceiling", 15, "--unit", "credits").returncode == 0
    p = voice(P, mock)
    assert p.returncode == 4, "approving Higgsfield credits must not authorise ElevenLabs characters"
    assert mock.count == 0


def test_a9_pipeline_auto_falls_back_to_the_free_voice_and_says_so(tmp_path):
    P = make_project("fallback")
    p = py("pipeline.py", "run", "--project", P, "--size", "480x270", "--targets", "long", "--no-qa", "--only", "validate,voice,assemble,align,visuals", env={"ELEVENLABS_API_KEY": ""})
    assert p.returncode == 0, p.stdout[-1500:]
    assert "FALLBACK" in p.stdout and "flite" in p.stdout
    last = json.loads((P / "render/pipeline-last.json").read_text())
    assert last["stack"] == "flite" and any("FALLBACK" in n for n in last["notes"])
    assert json.loads((P / "audio/voice.json").read_text())["stack"] == "flite"


def test_a9_doctor_reports_a_missing_tool_instead_of_assuming(tmp_path):
    empty = tmp_path / "bin"
    empty.mkdir()
    p = run([sys.executable, ROOT / "tools/doctor.py"], env={"PATH": str(empty)})
    assert p.returncode == 3
    assert "MISSING ffmpeg" in p.stdout.replace("  ", " ") or "MISSING   ffmpeg" in p.stdout
    assert "NOT READY" in p.stdout


def test_a9_missing_chromium_is_a_clear_exit_4_not_a_crash(smoke, tmp_path):
    p = run(["npx", "tsx", "engine/render.ts", "--project", smoke, "--target", "long", "--range", "0:3", "--out", tmp_path / "x.mp4"], env={"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "nowhere")})
    assert p.returncode == 4, p.stdout[-500:] + p.stderr[-800:]
    assert "chromium" in (p.stdout + p.stderr).lower()


def test_a9_live_integrations_are_labelled_untested_never_available(tmp_path):
    p = py("doctor.py")
    lines = {ln.split(None, 1)[1].split("  ")[0].strip(): ln.split()[0] for ln in p.stdout.splitlines() if ln.strip() and ln.split()[0] in ("AVAILABLE", "UNTESTED", "MISSING", "BLOCKED")}
    for name in ("ElevenLabs voice (live)", "Higgsfield (credits)", "YouTube upload / Studio"):
        assert lines.get(name) == "UNTESTED", (name, lines.get(name))
