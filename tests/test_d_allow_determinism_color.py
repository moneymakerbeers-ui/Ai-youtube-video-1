"""What the QA is allowed to tolerate is narrow and comes from the plan; the render is deterministic; colours survive encoding; and the plan builder
warns about transitions the operator cannot make exact."""
import json, pathlib, shutil
import numpy as np
import pytest
from conftest import ROOT, ffprobe, make_project, py, run


def jl(p):
    return json.loads(pathlib.Path(p).read_text())


@pytest.mark.parametrize("t", ["long", "S01"])
def test_allow_lists_are_narrow_and_come_from_the_plan(smoke, t):
    plan, allow = jl(smoke / f"render/plan-{t}.json"), jl(smoke / f"qa/allow-{t}.json")
    D = plan["durationS"]
    # black: only the declared opening fade and ending fade/hold, each exactly as long as declared
    want = []
    if plan["opening"]["fadeInMs"]:
        want.append((0.0, plan["opening"]["fadeInMs"] / 1000))
    if plan["ending"]["fadeOutMs"] + plan["ending"]["holdBlackMs"]:
        want.append((D - (plan["ending"]["fadeOutMs"] + plan["ending"]["holdBlackMs"]) / 1000, D))
    got = [(b["fromS"], b["toS"]) for b in allow["black"]]
    assert len(got) == len(want) and all(abs(g[0] - w[0]) < 0.01 and abs(g[1] - w[1]) < 0.01 for g, w in zip(got, want)), (got, want)
    assert sum(b - a for a, b in got) < 1.0
    # holds are exactly the plan's declared holds; rests are bounded; nothing covers the whole film
    holds = [(f["fromS"], f["toS"]) for f in allow["freeze"] if f["kind"] == "hold"]
    declared = [(s["hold"]["fromS"], s["hold"]["toS"]) for s in plan["scenes"] if s.get("hold")]
    assert holds == declared
    assert all(f.get("reason") for f in allow["freeze"]) and all(f["maxS"] <= allow["restMaxS"] for f in allow["freeze"] if f["kind"] == "rest")
    assert sum(b - a for a, b in holds) < 0.6 * D
    # silence: only what the assembler recorded
    asm = jl(smoke / ("audio/assembly.json" if t == "long" else f"audio/shorts/{t}/assembly.json"))
    assert len(allow["silence"]) <= len(asm["silences"])
    # no catch-all key of the v2 kind
    assert not {"blanket", "all", "anywhere", "tailBlack", "headSilence"} & set(allow)


def test_without_declared_fades_nothing_black_is_tolerated(smoke, tmp_path):
    plan = jl(smoke / "render/plan-long.json")
    plan["opening"]["fadeInMs"], plan["ending"]["fadeOutMs"], plan["ending"]["holdBlackMs"] = 0, 0, 0
    pf = tmp_path / "plan.json"
    pf.write_text(json.dumps(plan))
    out = tmp_path / "allow.json"
    p = py("make_allow.py", "--plan", pf, "--tokens", smoke / "style-tokens.json", "--thresholds", ROOT / "library/thresholds.json", "--out", out)
    assert p.returncode == 0 and jl(out)["black"] == [], "v2 tolerated black at the end of every file; v3 tolerates none unless declared"


def test_plan_lint_names_the_unplanned_stillness_before_any_render(smoke, tmp_path):
    ok = py("make_allow.py", "--plan", smoke / "render/plan-long.json", "--tokens", smoke / "style-tokens.json", "--thresholds", ROOT / "library/thresholds.json", "--check")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    plan = jl(smoke / "render/plan-long.json")
    s = plan["scenes"][2]  # a scene whose entities, camera and hold are removed: nothing is scheduled for its whole length
    s["entities"], s["camera"] = [], []
    s.pop("hold", None)
    pf = tmp_path / "plan.json"
    pf.write_text(json.dumps(plan))
    bad = py("make_allow.py", "--plan", pf, "--tokens", smoke / "style-tokens.json", "--thresholds", ROOT / "library/thresholds.json", "--check")
    assert bad.returncode == 1 and s["id"] in (bad.stdout + bad.stderr), "the lint must exit 1 and name the scene"
    assert any(w in (bad.stdout + bad.stderr) for w in ("entrance", "camera", "hold", "motion")), "and say what to do about it"


def test_plan_warns_when_an_operator_cannot_match_the_anchor_sizes(smoke):
    P = make_project("clamp-warning")
    shutil.copytree(smoke / "audio", P / "audio", dirs_exist_ok=True)
    sc = jl(P / "scenes.json")
    sc["scenes"][0]["layouts"]["landscape"]["placements"]["e_frame"]["w"] = 0.08
    sc["scenes"][1]["layouts"]["landscape"]["placements"]["e_frame2"]["w"] = 0.9
    (P / "scenes.json").write_text(json.dumps(sc))
    p = py("make_plan.py", "--project", P, "--target", "long", "--size", "640x360", "--auto-fit", "--out", P / "render/plan-long.json")
    assert p.returncode == 0, p.stdout + p.stderr
    w = [x for x in jl(P / "render/plan-long.json")["warnings"] if "s01>s02" in x]
    assert w and "truthful_morph" in w[0] and "11.2x" in w[0] and "at most 8x" in w[0], w
    # the unmodified example has no such warning
    assert not [x for x in jl(smoke / "render/plan-long.json")["warnings"] if "differ in width" in x]


# ───────── determinism and colour ─────────
@pytest.mark.parametrize("target,again,ref", [("long", "out/again.mp4", "out/full-video.mp4"), ("S01", "out/again-s01.mp4", "out/short-01.mp4")])
def test_the_render_is_deterministic_byte_for_byte(smoke, target, again, ref):
    """Same plan, same worker count (the pipeline's default, 2) -> the same bytes. Regression: a first-come-first-served frame queue made a page's
    history, and with it the pixels at text edges, depend on thread timing: the demo Short differed between runs in up to 120 of 425 frames (up to 44
    luma levels) while its scene-graph states were identical. Checked on the long video and on the Short, the file that showed it."""
    from common import sha256_file
    P = make_project(f"determinism-{target}")
    shutil.rmtree(P)
    shutil.copytree(smoke, P, symlinks=True)
    r = run(["npx", "tsx", "engine/render.ts", "--project", P, "--target", target, "--out", again], timeout=900)
    assert r.returncode == 0, r.stdout[-1500:]
    assert sha256_file(str(P / again)) == sha256_file(str(smoke / ref)), "two renders of the same plan must be identical files"
    a, b = jl(smoke / f"render/trace-{target}.json"), jl(P / f"render/trace-{target}.json")
    assert a["frameHashes"] == b["frameHashes"] and a["stateHashes"] == b["stateHashes"], "identical frames and identical scene-graph states"


def test_colours_survive_encoding(smoke, tmp_path):
    """The renderer's PNG frame vs the same frame decoded from the delivered mp4 (bt709, tv range tags honoured): the encode must not shift colour."""
    from PIL import Image
    P = make_project("colour")
    shutil.rmtree(P)
    shutil.copytree(smoke, P, symlinks=True)
    n = 180  # frame 180 = 6.0 s: scene s03 with the chart
    r = run(["npx", "tsx", "engine/render.ts", "--project", P, "--target", "long", "--dump-frames", str(n), "--dump-dir", tmp_path, "--audio", "none"], timeout=600)
    assert r.returncode == 0, r.stdout[-800:]
    src = np.asarray(Image.open(tmp_path / f"long-f{n:06d}.png").convert("RGB"), dtype=float)
    dec = tmp_path / "dec.png"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", smoke / "out/full-video.mp4", "-vf", f"select=eq(n\\,{n}),scale=in_range=tv:out_range=pc:in_color_matrix=bt709:out_color_matrix=bt709,format=rgb24", "-frames:v", "1", dec], check=True)
    got = np.asarray(Image.open(dec).convert("RGB"), dtype=float)
    assert got.shape == src.shape
    err = np.abs(got - src)
    mse = float(((got - src) ** 2).mean())
    psnr = 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)
    assert psnr >= 36, f"PSNR {psnr:.1f} dB: the encode changed the picture"
    # a systematic colour shift (wrong matrix or range) shows as a per-channel mean offset, which noise does not
    assert float(np.abs((got - src).mean(axis=(0, 1))).max()) < 1.5, f"per-channel mean shift {(got - src).mean(axis=(0, 1))}"
    assert float(np.percentile(err, 99)) < 25
    v = ffprobe(smoke / "out/full-video.mp4")["video"]
    assert (v["color_space"], v["color_primaries"], v["color_transfer"], v["color_range"]) == ("bt709", "bt709", "bt709", "tv")
