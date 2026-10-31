"""Acceptance 4 and 5: references must resolve (validation fails otherwise), and a Short with its own voice lines gets its own aligned audio."""
import hashlib, json, pathlib, shutil, sys
import pytest
from conftest import ROOT, make_project, py, run


def validate(P):
    return run(["npx", "tsx", "schema/validate.ts", "project", P])


def load(P, name):
    return json.loads((pathlib.Path(P) / name).read_text())


def save(P, name, d):
    (pathlib.Path(P) / name).write_text(json.dumps(d, indent=2))


# ───────── A4: a scene that cites a claim or asset that does not exist fails validation, naming the id ─────────
def test_a4_baseline_project_validates(smoke):
    p = validate(smoke)
    assert p.returncode == 0, p.stdout + p.stderr


def test_a4_missing_claim_reference_fails_validation(tmp_path):
    P = make_project("val-claim")
    sc = load(P, "scenes.json")
    sc["scenes"][0]["claimIds"] = ["C99"]
    save(P, "scenes.json", sc)
    p = validate(P)
    assert p.returncode != 0
    assert "unknown claim C99" in p.stdout + p.stderr, p.stdout + p.stderr


def test_a4_missing_asset_reference_fails_validation(tmp_path):
    P = make_project("val-asset")
    sc = load(P, "scenes.json")
    sc["scenes"][0]["entities"][0]["assetId"] = "A99"
    save(P, "scenes.json", sc)
    p = validate(P)
    assert p.returncode != 0
    assert "unknown asset A99" in p.stdout + p.stderr, p.stdout + p.stderr


def test_a4_short_referring_to_a_missing_scene_fails_validation():
    P = make_project("val-short")
    sh = load(P, "shorts.json")
    sh["shorts"][0]["sceneIds"] = ["s01", "s99"]
    save(P, "shorts.json", sh)
    p = validate(P)
    assert p.returncode != 0 and "s99" in p.stdout + p.stderr, p.stdout + p.stderr


def test_a4_evidence_pointing_at_a_missing_or_changed_snapshot_fails_the_evidence_check(tmp_path):
    P = make_project("val-evidence")
    (P / "research" / "sources").mkdir(parents=True)
    text = "Light from the sun is a mixture of every colour, and the sky scatters blue light most strongly."
    snap = P / "research/sources/s1.txt"
    snap.write_text(text)
    facts = {"claims": [{
        "id": "C01", "text": "The sky scatters blue light most strongly.", "sources": [{"title": "t", "url": "https://example.org/a", "type": "reference", "accessed": "2026-10-30"}],
        "evidence": [{"sourceIndex": 0, "locator": {"kind": "quote", "value": "q"}, "quote": "the sky scatters blue light most strongly", "snapshot": "research/sources/s1.txt",
                      "snapshotSha256": hashlib.sha256(text.encode()).hexdigest(), "supports": "direct", "interpretation": "states the claim in so many words"}],
        "status": "single_source"}]}
    save(P, "facts.json", facts)
    sc = load(P, "scenes.json")
    sc["scenes"][0]["claimIds"] = ["C01"]
    save(P, "scenes.json", sc)
    ok = py("check_evidence.py", "--project", P)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    # 1: the quote is not in the snapshot
    facts["claims"][0]["evidence"][0]["quote"] = "the sky scatters red light most strongly"
    save(P, "facts.json", facts)
    bad = py("check_evidence.py", "--project", P)
    assert bad.returncode == 1 and "quote is not in" in bad.stdout, bad.stdout
    facts["claims"][0]["evidence"][0]["quote"] = "the sky scatters blue light most strongly"
    # 2: the snapshot changed after the claim was written
    snap.write_text(text + " (edited)")
    save(P, "facts.json", facts)
    bad = py("check_evidence.py", "--project", P)
    assert bad.returncode == 1 and "sha256" in bad.stdout, bad.stdout
    # 3: the snapshot is gone
    snap.unlink()
    bad = py("check_evidence.py", "--project", P)
    assert bad.returncode == 1 and "not in the project" in bad.stdout, bad.stdout


def test_a4_number_the_narration_speaks_must_be_in_the_source(tmp_path):
    P = make_project("val-number")
    (P / "research" / "sources").mkdir(parents=True)
    text = "The atom is about 0.1 nanometres across. Its nucleus is roughly 100,000 times smaller."
    (P / "research/sources/s1.txt").write_text(text)
    sha = hashlib.sha256(text.encode()).hexdigest()
    facts = {"claims": [{"id": "C01", "text": "An atom is about 0.1 nanometres across.", "sources": [{"title": "t", "url": "https://example.org/a", "type": "reference", "accessed": "2026-10-30"}],
             "evidence": [{"sourceIndex": 0, "locator": {"kind": "quote", "value": "q"}, "quote": "The atom is about 0.1 nanometres across.", "snapshot": "research/sources/s1.txt", "snapshotSha256": sha, "supports": "direct", "interpretation": "states the size directly"}], "status": "single_source"}]}
    save(P, "facts.json", facts)
    sc = load(P, "scenes.json")
    sc["scenes"][0]["claimIds"] = ["C01"]
    sc["scenes"][0]["narration"] = "An atom is about 0.1 nanometres across."
    save(P, "scenes.json", sc)
    assert py("check_evidence.py", "--project", P).returncode == 0
    sc["scenes"][0]["narration"] = "An atom is about 5 nanometres across."
    save(P, "scenes.json", sc)
    bad = py("check_evidence.py", "--project", P, "--strict")
    assert bad.returncode == 1 and "narration says 5" in bad.stdout, bad.stdout


def test_a4_model_processed_snapshots_are_never_reported_as_proof(tmp_path):
    P = make_project("val-modelproc")
    (P / "research" / "sources").mkdir(parents=True)
    text = "An atom is about 0.1 nanometres across."
    (P / "research/sources/s1.txt").write_text(text)
    facts = {"claims": [{"id": "C01", "text": "An atom is about 0.1 nanometres across.", "sources": [{"title": "t", "url": "https://example.org/a", "type": "reference", "accessed": "2026-10-30"}],
             "evidence": [{"sourceIndex": 0, "locator": {"kind": "quote", "value": "q"}, "quote": "An atom is about 0.1 nanometres across.", "snapshot": "research/sources/s1.txt", "snapshotSha256": hashlib.sha256(text.encode()).hexdigest(), "snapshotKind": "model_processed", "supports": "direct", "interpretation": "states the size directly"}], "status": "single_source"}]}
    save(P, "facts.json", facts)
    p = py("check_evidence.py", "--project", P)
    rep = json.loads((P / "review/evidence-check.json").read_text())
    assert rep["summary"]["humanNeeded"] >= 1
    assert any(f["check"] == "model_processed" and f["kind"] == "human_needed" for f in rep["findings"])
    assert all(f["action"] for f in rep["findings"] if f["severity"] in ("error", "warn")), "every failure must say what to do"


# ───────── A5: a Short with new voice lines has its own assembled audio, aligned on that audio ─────────
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def test_a5_short_has_its_own_audio_and_alignment(smoke):
    P = pathlib.Path(smoke)
    long_a = json.loads((P / "audio/alignment.json").read_text())
    short_dir = P / "audio/shorts/S01"
    short_a = json.loads((short_dir / "alignment.json").read_text())
    plan = json.loads((P / "render/plan-S01.json").read_text())
    # the alignment is bound to the Short's own file, which is not the parent narration
    assert sha(short_dir / "narration.wav") == short_a["audio"]["sha256"]
    assert short_a["audio"]["sha256"] != long_a["audio"]["sha256"]
    # the Short has words the parent does not (its opening and closing lines), spoken and aligned on its own file
    joined = " ".join(str(w["w"]).lower().strip(".,") for w in short_a["words"])
    assert "watch one frame change shape" in joined and "same frame two shapes" in joined, joined
    parent = " ".join(str(w["w"]).lower().strip(".,") for w in long_a["words"])
    assert "watch one frame change shape" not in parent and "same frame two shapes" not in parent
    # it is not the parent's timestamps copied: the shared scene's first word moved by about the opening line's length
    first_long = next(w for w in long_a["words"] if w["scene"] == "s01")
    first_short = next(w for w in short_a["words"] if w["scene"] == "s01")
    shift = first_short["s"] - first_long["s"]
    assert shift > 0.8, f"the Short's scene s01 starts only {shift:.2f}s later than in the long video: timestamps look copied"
    # relative spacing inside the shared scene is preserved to within alignment error, which shows the audio really is the same speech
    a = [w for w in long_a["words"] if w["scene"] == "s01"][:6]
    b = [w for w in short_a["words"] if w["scene"] == "s01"][:6]
    for x, y in zip(a, b):
        assert abs((y["s"] - first_short["s"]) - (x["s"] - first_long["s"])) < 0.12
    # and the render plan uses the Short's file and hash, not the parent's
    assert plan["audio"]["sha256"] == short_a["audio"]["sha256"]
    assert "shorts/S01" in plan["audio"]["file"] and plan["durationS"] == pytest.approx(short_a["audio"]["durationS"], abs=0.05)


def test_a5_stale_short_audio_is_refused_by_the_planner(tmp_path):
    P = make_project("short-stale")
    ok = py("pipeline.py", "run", "--project", P, "--size", "480x270", "--targets", "long,S01", "--no-qa", timeout=900)
    assert ok.returncode == 0, ok.stdout[-2500:]
    # change the Short's audio after it was aligned: planning from the old alignment would desynchronise captions and visuals
    wav = P / "audio/shorts/S01/narration.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-af", "atrim=0:5", tmp_path / "short.wav"], check=True)
    shutil.copy(tmp_path / "short.wav", wav)
    p = py("make_plan.py", "--project", P, "--target", "S01", "--size", "480x270")
    assert p.returncode == 2 and ("hash" in (p.stdout + p.stderr).lower() or "stale" in (p.stdout + p.stderr).lower()), p.stdout + p.stderr
