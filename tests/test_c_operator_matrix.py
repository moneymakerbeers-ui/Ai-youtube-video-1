"""Every transition operator, in both aspect ratios, on REAL rendered frames and judged by the same motion gate the pipeline uses.
One 9-scene project (a different shape per scene, so every anchor really travels and scales), planned as 16:9 and as 9:16 from the same scene data."""
import copy, json, pathlib
import pytest
from conftest import ROOT, checks, make_project, py, run

OPS = ["dissolve", "match_geometry", "focus_bridge", "truthful_morph", "match_movement", "nested_scale", "occlusion_reveal", "depth_through_object"]
XS = [0.28, 0.62, 0.40, 0.70, 0.33, 0.55, 0.45, 0.66, 0.5]
WS = [0.30, 0.22, 0.34, 0.26, 0.20, 0.32, 0.24, 0.30, 0.28]
YS = [0.40, 0.45, 0.38, 0.50, 0.42, 0.40, 0.50, 0.42, 0.45]
WORDS = "Every scene here carries a single shape that the next scene must answer.".split()


def build(P):
    sc = json.loads((P / "scenes.json").read_text())
    tpl = copy.deepcopy(sc["scenes"][0])
    scenes = []
    for k in range(len(OPS) + 1):
        s = copy.deepcopy(tpl)
        s.update(id=f"m{k}", narration=" ".join(WORDS[: 10 + k % 3]), visualIntensity=1)
        s.pop("signature", None), s.pop("shortIds", None)
        f, t = f"f{k}", f"t{k}"
        s["entities"] = [{"id": f, "role": "diagram", "visual": {"component": "aspect_frame", "props": {"ratioW": 16 if k % 2 == 0 else 9, "ratioH": 9 if k % 2 == 0 else 16}}, "enter": {"style": "draw", "durationMs": 700}},
                         {"id": t, "role": "label", "text": f"Scene {k}", "enterAtWord": 3}]
        cam = [{"from": {"x": 0.5, "y": 0.5, "scale": 1.0}, "to": {"x": 0.5, "y": 0.5, "scale": 1.05}, "startWord": 0, "endWord": 6, "reason": "a slow push so the scene is never dead"}] if k % 2 else []
        s["layouts"] = {"landscape": {"placements": {f: {"x": XS[k], "y": YS[k], "w": WS[k]}, t: {"x": 0.5, "y": 0.8, "w": 0.3, "z": 2}}, "camera": cam},
                        "portrait": {"placements": {f: {"x": 0.5, "y": 0.3 + 0.03 * (k % 3), "w": 0.5 + 0.05 * (k % 3)}, t: {"x": 0.5, "y": 0.6, "w": 0.4, "z": 2}}, "camera": []}}
        if k < len(OPS):
            tr = {"type": OPS[k]}
            if OPS[k] != "dissolve":
                tr.update(rationale=f"{OPS[k]} between two shapes in the operator matrix", anchorFrom={"entityId": f}, anchorTo={"entityId": f"f{k + 1}"})
            s["transition"] = tr
        else:
            s["transition"] = {"type": "cut"}
        scenes.append(s)
    sc["scenes"] = scenes
    (P / "scenes.json").write_text(json.dumps(sc, indent=1))
    (P / "shorts.json").unlink()
    cfg = json.loads((P / "config.json").read_text())
    cfg["videoIdea"] = "operator matrix"
    (P / "config.json").write_text(json.dumps(cfg))
    return [s["id"] for s in scenes]


@pytest.fixture(scope="module")
def matrix():
    P = make_project("opmatrix")
    ids = build(P)
    v = run(["npx", "tsx", "schema/validate.ts", "project", P])
    assert v.returncode == 0, v.stdout[-1500:]
    for target, size in (("preview", "640x360"), ("preview-portrait", "360x640")):
        p = py("make_plan.py", "--project", P, "--target", target, "--scenes", ",".join(ids), "--size", size, "--auto-fit", "--out", P / f"render/plan-{target}.json")
        assert p.returncode == 0, p.stdout + p.stderr
        r = run(["npx", "tsx", "engine/render.ts", "--project", P, "--target", target, "--plan", P / f"render/plan-{target}.json", "--audio", "none", "--allow-placeholders", "--out", f"out/{target}.mp4"], timeout=900)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-800:]
    return P


@pytest.mark.parametrize("target", ["preview", "preview-portrait"])
def test_every_operator_renders_as_planned_and_passes_the_motion_gate(matrix, target):
    P = matrix
    tr = json.loads((P / f"render/trace-{target}.json").read_text())
    used = {(t["planned"], t["used"], t["fellBack"]) for t in tr["transitions"]}
    assert {u[0] for u in used} == set(OPS), "all eight operators are in the render"
    assert all(planned == usedt and not fb for planned, usedt, fb in used), f"no operator may silently fall back to a dissolve: {used}"
    out = P / f"qa/motion-{target}.json"
    p = py("qa_motion.py", P / f"out/{target}.mp4", "--plan", P / f"render/plan-{target}.json", "--trace", P / f"render/trace-{target}.json", "--thresholds", ROOT / "library/thresholds.json", "--out", out, "--no-previews")
    rep = json.loads(out.read_text())
    assert p.returncode == 0 and rep["overall"] == "PASSED", [(c["id"], c["status"], c["detail"]) for c in rep["checks"] if c["status"] in ("fail", "blocked", "warn")]
    for i, op in enumerate(OPS):
        tid = f"m{i}>m{i + 1}"
        for what in ("boundary", "exposure", "stall", "pop"):
            c = checks(rep, f"motion.{tid}.{what}")
            assert c and c[0]["status"] == "pass", (op, target, what)
        if op != "dissolve":
            a = checks(rep, f"motion.{tid}.anchor")
            assert a and a[0]["status"] == "pass" and a[0]["value"] >= 15, (op, target, "anchors measured on every frame of the move")


@pytest.mark.parametrize("target,wh", [("preview", (640, 360)), ("preview-portrait", (360, 640))])
def test_matrix_files_have_the_right_shape_and_no_decode_errors(matrix, target, wh):
    from conftest import ffprobe
    f = matrix / f"out/{target}.mp4"
    v = ffprobe(f)["video"]
    assert (v["width"], v["height"]) == wh and v["pix_fmt"] == "yuv420p" and v["color_space"] == "bt709"
    p = run(["ffmpeg", "-v", "error", "-nostdin", "-i", f, "-f", "null", "-"])
    assert p.returncode == 0 and p.stderr.strip() == ""


def test_the_same_scene_data_drives_both_shapes(matrix):
    """16:9 and 9:16 plans come from the same scenes: identical scene and entity ids and the same transition operators, but different geometry."""
    L, S = (json.loads((matrix / f"render/plan-{t}.json").read_text()) for t in ("preview", "preview-portrait"))
    assert [s["id"] for s in L["scenes"]] == [s["id"] for s in S["scenes"]]
    assert [(s["id"], (s.get("transitionOut") or {}).get("type")) for s in L["scenes"]] == [(s["id"], (s.get("transitionOut") or {}).get("type")) for s in S["scenes"]]
    for a, b in zip(L["scenes"], S["scenes"]):
        assert sorted(e["id"] for e in a["entities"]) == sorted(e["id"] for e in b["entities"])
    assert (L["width"], L["height"]) == (640, 360) and (S["width"], S["height"]) == (360, 640)
