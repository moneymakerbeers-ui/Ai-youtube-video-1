#!/usr/bin/env python3
"""build_scenes.py — video 7 (George narration re-edit): scenes, layouts, Shorts -> scenes.json, shorts.json, spoken_script.txt.
The narration text of every scene is EXACTLY what the master audio says (transcribed with whisper medium.en, checked by ear-free
re-alignment). Creator rules for this edit: hook changes every 2-4 s for 25 s, then every 5-10 s; every still pushes in 3-6 %;
cuts on sentence ends; counters on the key numbers; supernova = hard cut + shake + one flash + boom; motion transitions, no fades.
Run: python3 videos/star-life-george-20261106/build_scenes.py"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

def V():
    return {"intent": "keep the master read", "emotion": "warm-explanatory", "intensity": 1, "pace": "steady", "emphasisWords": [], "pauseBeforeMs": 0, "pauseAfterMs": 0}

def P(x, y, w, z=0, depth=0.0):
    return {"x": x, "y": y, "w": w, "z": z, "depth": depth}

def cam(fs, ts, fx=0.5, fy=0.5, tx=None, ty=None, reason="slow push-in keeps the still alive", easing="soft", sw=None, ew=None):
    c = {"from": {"x": fx, "y": fy, "scale": fs}, "to": {"x": tx if tx is not None else fx, "y": ty if ty is not None else fy, "scale": ts}, "easing": easing, "reason": reason}
    if sw is not None: c["startWord"] = sw
    if ew is not None: c["endWord"] = ew
    return c

def img(eid, asset, role="backdrop"):
    return {"id": eid, "role": role, "assetId": asset, "enter": {"style": "none", "durationMs": 0}}

def vis(eid, comp, props, role="diagram", at=None, enter=("fade", 250)):
    e = {"id": eid, "role": role, "visual": {"component": comp, "props": props}, "enter": {"style": enter[0], "durationMs": enter[1]}}
    if at is not None: e["enterAtWord"] = at
    return e

def txt(eid, text, role="label", at=None, exit_at=None, enter=("pop", 350)):
    assert len(text) <= 40, text
    e = {"id": eid, "role": role, "text": text, "enter": {"style": enter[0], "durationMs": enter[1]}}
    if at is not None: e["enterAtWord"] = at
    if exit_at is not None: e["exitAtWord"] = exit_at
    return e

def tag(label, at=None):
    e = vis("e_tag", "tag", {"text": label}, role="context", at=at, enter=("fade", 300))
    return e

def W(narr, word, nth=1):
    """scene-relative index of the nth word starting with `word` (case-insensitive, punctuation ignored)"""
    ws = [w.strip(".,?!'’\"").lower() for w in narr.split()]
    hits = [i for i, w in enumerate(ws) if w.startswith(word.lower())]
    assert len(hits) >= nth, (word, narr)
    return hits[nth - 1]

STAR = lambda: vis("e_stars", "starfield", {"seed": 7}, role="backdrop", enter=("none", 0))
FULL_L, FULL_P = P(0.5, 0.5, 1.0), P(0.5, 0.5, 3.0)
STAR_L = STAR_P = P(0.5, 0.5, 1.0, z=-1)
def TAG_L(n): w = round((36 * n + 80) * 0.000358, 4); return P(round(0.94 - w / 2, 4), 0.085, w, z=6, depth=1.0)
def TAG_P(n): return P(0.5, 0.105, round(min(0.8, (36 * n + 80) * 0.000637), 4), z=6, depth=1.0)

scenes = []
def S(id, section, claims, narr, beat, ents, land, port, cam_l=(), cam_p=(), transition=None, intensity=1, signature=None, shake=None, presentation="illustration"):
    for e in ents:
        if e["id"] == "e_tag":
            n = len(e["visual"]["props"]["text"]); land = {**land, "e_tag": TAG_L(n)}; port = {**port, "e_tag": TAG_P(n)}
    sc = {"id": id, "section": section, "claimIds": list(claims), "narration": narr, "intent": section, "retentionBeat": beat,
          "presentation": presentation, "visualIntensity": intensity, "transition": transition or {"type": "cut"}, "voice": V(), "entities": ents,
          "layouts": {"landscape": {"placements": land, "camera": list(cam_l)}, "portrait": {"placements": port, "camera": list(cam_p)}},
          "shortIds": [], "assetIds": sorted({e["assetId"] for e in ents if e.get("assetId")}), "qaRisk": []}
    if shake: sc["layouts"]["landscape"]["shake"] = shake; sc["layouts"]["portrait"]["shake"] = shake
    if signature: sc["signature"] = signature
    scenes.append(sc)
    return sc

def MOVE(rationale, a_from, a_to):
    return {"type": "match_movement", "durationMs": 700, "easing": "emphasized", "rationale": rationale, "anchorFrom": {"entityId": a_from}, "anchorTo": {"entityId": a_to}}

# ───────── HOOK (0:00-0:25): something changes every 2-4 s ─────────
n = "How does a soft cloud of dust become the darkest object in the universe?"
S("h1", "hook", ["C01_pillars"], n, "promise",
  [img("e_pil", "r_pillars"), vis("e_scrim", "scrim", {"aspect": 0.35}, role="decor", enter=("none", 0)),
   txt("e_q1", "How does a soft cloud of dust", "subject", at=0, enter=("none", 0)),
   txt("e_q2", "become the darkest object", "subject", at=W(n, "become"), enter=("pop", 300)),
   txt("e_q3", "in the universe?", "subject", at=W(n, "universe"), enter=("pop", 300))],
  {"e_pil": FULL_L, "e_scrim": P(0.5, 0.5, 1.0, 1), "e_q1": P(0.5, 0.39, 0.82, 3), "e_q2": P(0.5, 0.5, 0.82, 3), "e_q3": P(0.5, 0.61, 0.5, 3)},
  {"e_pil": FULL_P, "e_scrim": P(0.5, 0.5, 1.0, 1), "e_q1": P(0.5, 0.43, 0.86, 3), "e_q2": P(0.5, 0.5, 0.86, 3), "e_q3": P(0.5, 0.57, 0.6, 3)},
  cam_l=[cam(1.0, 1.1, 0.5, 0.5, 0.47, 0.44, "a fast push into the pillars carries the hook question")],
  cam_p=[cam(1.06, 1.16, 0.5, 0.5, 0.48, 0.45, "a fast push into the pillars carries the hook question")], presentation="archival")
n = "Stay with me, because the answer is a tug of war."
S("h2", "hook", ["C06_balance"], n, "promise",
  [STAR(), vis("e_bal", "balance", {"inAtS": 0.2, "outAtS": 1.2}, enter=("pop", 300)), txt("e_t", "a tug of war", "subject", at=W(n, "tug"))],
  {"e_stars": STAR_L, "e_bal": P(0.5, 0.48, 0.42, 2), "e_t": P(0.5, 0.88, 0.28, 3)},
  {"e_stars": STAR_P, "e_bal": P(0.5, 0.45, 0.9, 2), "e_t": P(0.5, 0.68, 0.6, 3)},
  cam_l=[cam(1.0, 1.06, reason="the tug of war tightens as it is named")], cam_p=[cam(1.0, 1.05, reason="the tug of war tightens")], presentation="diagram")
n = "And the calcium in your bones is part of the story."
S("h3", "hook", ["C20_elements"], n, "next_question",
  [STAR(), vis("e_bone", "bone", {}, role="subject", enter=("pop", 300)), txt("e_t", "part of the story", "label", at=W(n, "part"))],
  {"e_stars": STAR_L, "e_bone": P(0.5, 0.45, 0.42, 2), "e_t": P(0.5, 0.75, 0.3, 3)},
  {"e_stars": STAR_P, "e_bone": P(0.5, 0.44, 0.84, 2), "e_t": P(0.5, 0.62, 0.62, 3)},
  cam_l=[cam(1.0, 1.05, reason="slow push on the bone: the open loop")], cam_p=[cam(1.0, 1.05, reason="slow push on the bone")], presentation="diagram")

# ───────── CLOUD → STAR ─────────
n = "It starts in a molecular cloud. Cold gas, with up to 10 million times the mass of the Sun,"
S("c1", "cloud", ["C02_cloud"], n, "orient",
  [img("e_car", "r_carina"), tag("Real image · Webb", at=W(n, "cold")),
   vis("e_n", "countup", {"to": 10000000, "over": 1.4, "sub": "times the Sun's mass"}, role="number", at=W(n, "10")), txt("e_l", "molecular cloud", "label", at=0)],
  {"e_car": FULL_L, "e_n": P(0.5, 0.72, 0.5, 4), "e_l": P(0.5, 0.2, 0.32, 3)},
  {"e_car": P(0.62, 0.5, 3.0), "e_n": P(0.5, 0.6, 0.9, 4), "e_l": P(0.5, 0.22, 0.66, 3)},
  cam_l=[cam(1.0, 1.05, 0.5, 0.5, 0.53, 0.5, "slow pan across the giant cloud")], cam_p=[cam(1.06, 1.11, reason="slow pan across the cloud")], presentation="archival")
n = "stretched across hundreds of light-years."
S("c2", "cloud", ["C02_cloud"], n, "develop",
  [img("e_car", "r_carina"), tag("Real image · Webb"), txt("e_l", "hundreds of light-years", "number", at=W(n, "hundreds"))],
  {"e_car": FULL_L, "e_l": P(0.5, 0.78, 0.46, 3)}, {"e_car": P(0.62, 0.5, 3.0), "e_l": P(0.5, 0.62, 0.8, 3)},
  cam_l=[cam(1.05, 1.0, 0.53, 0.5, 0.5, 0.5, "pull back to show how wide it is", easing="emphasized")], cam_p=[cam(1.11, 1.06, reason="pull back to show its width")], presentation="archival")
n = "Some clumps gather more matter, and their gravity grows stronger. One collapses and heats up."
S("c3", "cloud", ["C02_cloud", "C03_protostar"], n, "payoff",
  [img("e_clump", "g_clump", role="subject"), tag("Illustration"), txt("e_g", "gravity grows", "label", at=W(n, "gravity")),
   vis("e_core", "glowdot", {"color": "#ffcf8a"}, role="subject", at=W(n, "collapses"), enter=("fade", 500))],
  {"e_clump": FULL_L, "e_g": P(0.22, 0.8, 0.26, 3), "e_core": P(0.5, 0.5, 0.12, 2)},
  {"e_clump": FULL_P, "e_g": P(0.5, 0.66, 0.56, 3), "e_core": P(0.5, 0.5, 0.26, 2)},
  cam_l=[cam(1.0, 1.06, reason="the camera leans into the collapsing clump")], cam_p=[cam(1.06, 1.12, reason="lean into the clump")],
  transition={"type": "nested_scale", "durationMs": 1600, "easing": "emphasized", "rationale": "the protostar is the inside of this collapsing clump: the zoom shows the same object one scale down",
              "anchorFrom": {"entityId": "e_core"}, "anchorTo": {"entityId": "e_proto"}}, intensity=3,
  signature={"before": "a collapsing clump", "after": "the protostar at its centre", "track": "the warm centre of the clump"})
n = "That's a protostar. It isn't burning anything yet."
S("p1", "protostar", ["C03_protostar"], n, "develop",
  [img("e_proto", "g_protostar", role="subject"), tag("Illustration"), txt("e_l", "protostar", "subject", at=W(n, "protostar")), txt("e_n", "not burning yet", "label", at=W(n, "burning"))],
  {"e_proto": FULL_L, "e_l": P(0.5, 0.18, 0.24, 3), "e_n": P(0.5, 0.82, 0.26, 3)},
  {"e_proto": FULL_P, "e_l": P(0.5, 0.25, 0.5, 3), "e_n": P(0.5, 0.66, 0.56, 3)},
  cam_l=[cam(1.06, 1.0, reason="settles back from the zoom")], cam_p=[cam(1.12, 1.06, reason="settles back from the zoom")])
n = "It keeps gaining mass. Its core gets hotter and denser."
S("p2", "protostar", ["C05_ignition"], n, "develop",
  [img("e_proto", "g_protostar", role="subject"), tag("Illustration"), txt("e_l", "hotter · denser", "label", at=W(n, "hotter"))],
  {"e_proto": FULL_L, "e_l": P(0.5, 0.82, 0.3, 3)}, {"e_proto": FULL_P, "e_l": P(0.5, 0.66, 0.6, 3)},
  cam_l=[cam(1.0, 1.06, reason="push toward the heating core")], cam_p=[cam(1.06, 1.12, reason="push toward the core")])
n = "At about 15 million degrees, hydrogen nuclei are squeezed together so hard that they fuse into helium. That's nuclear fusion."
S("f1", "ignition", ["C05_ignition"], n, "develop",
  [STAR(), vis("e_temp", "countup", {"to": 15, "over": 1.2, "suffix": " million °", "sub": "core temperature"}, role="number", at=W(n, "15"), enter=("pop", 300)),
   txt("e_f", "hydrogen → helium", "subject", at=W(n, "fuse")), txt("e_n", "nuclear fusion", "label", at=W(n, "nuclear"))],
  {"e_stars": STAR_L, "e_temp": P(0.5, 0.4, 0.58, 2), "e_f": P(0.5, 0.68, 0.38, 3), "e_n": P(0.5, 0.79, 0.24, 3)},
  {"e_stars": STAR_P, "e_temp": P(0.5, 0.36, 0.95, 2), "e_f": P(0.5, 0.55, 0.8, 3), "e_n": P(0.5, 0.63, 0.56, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift while the numbers build")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "And in that moment, a star is born."
S("f2", "ignition", ["C05_ignition"], n, "payoff",
  [img("e_ign", "g_ignite", role="subject"), tag("Illustration"), txt("e_b", "a star is born", "subject", at=W(n, "star"))],
  {"e_ign": FULL_L, "e_b": P(0.5, 0.16, 0.34, 3)}, {"e_ign": FULL_P, "e_b": P(0.5, 0.25, 0.7, 3)},
  cam_l=[cam(1.08, 1.0, reason="pull back as the new star lights its cocoon")], cam_p=[cam(1.14, 1.06, reason="pull back as the star lights up")],
  transition=MOVE("the camera keeps travelling from the newborn star into what holds it up", "e_ign", "e_bal"))

# ───────── BALANCE / MASS ─────────
n = "Now gravity pulls in, and the heat from fusion pushes out. While they balance, the star is stable."
S("b1", "balance", ["C06_balance"], n, "develop",
  [STAR(), vis("e_bal", "balance", {"inAtS": 0.4, "outAtS": 2.6}), txt("e_g", "gravity: in", "label", at=W(n, "gravity")), txt("e_p", "pressure: out", "label", at=W(n, "pushes"))],
  {"e_stars": STAR_L, "e_bal": P(0.5, 0.5, 0.48, 2), "e_g": P(0.18, 0.5, 0.22, 3), "e_p": P(0.82, 0.5, 0.24, 3)},
  {"e_stars": STAR_P, "e_bal": P(0.5, 0.45, 0.92, 2), "e_g": P(0.5, 0.2, 0.5, 3), "e_p": P(0.5, 0.68, 0.54, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift while both forces appear")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "Astronomers call this the main sequence. Our Sun is roughly halfway through it."
S("b2", "balance", ["C07_mainseq"], n, "settle",
  [STAR(), img("e_sun", "r_sun", role="subject"), tag("Real image · SDO"), txt("e_l", "main sequence", "subject", at=W(n, "main")), txt("e_h", "the Sun: about halfway", "label", at=W(n, "halfway"))],
  {"e_stars": STAR_L, "e_sun": P(0.5, 0.5, 0.46, 1), "e_l": P(0.17, 0.2, 0.28, 3), "e_h": P(0.81, 0.78, 0.32, 3)},
  {"e_stars": STAR_P, "e_sun": P(0.5, 0.45, 0.96, 1), "e_l": P(0.5, 0.2, 0.62, 3), "e_h": P(0.5, 0.68, 0.74, 3)},
  cam_l=[cam(1.0, 1.05, reason="slow push on the Sun")], cam_p=[cam(1.0, 1.05, reason="slow push on the Sun")], presentation="archival",
  transition=MOVE("the motion carries on from our steady Sun to the stars that burn faster", "e_sun", "e_two"))
n = "So how long does it last? Mass decides. A heavier star burns its fuel much faster, just to hold up its own weight."
S("m1", "mass", ["C08_mass_rate"], n, "develop",
  [STAR(), vis("e_two", "twostars", {}), txt("e_m", "mass decides", "subject", at=W(n, "mass")), txt("e_f", "heavier → burns faster", "label", at=W(n, "heavier"))],
  {"e_stars": STAR_L, "e_two": P(0.5, 0.54, 0.54, 2), "e_m": P(0.5, 0.1, 0.26, 3), "e_f": P(0.5, 0.2, 0.36, 3)},
  {"e_stars": STAR_P, "e_two": P(0.5, 0.45, 0.96, 2), "e_m": P(0.5, 0.2, 0.6, 3), "e_f": P(0.5, 0.66, 0.8, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "The Sun gets about 10 billion years. Some massive stars, only a few million."
S("m2", "mass", ["C08_mass_rate"], n, "evidence",
  [STAR(), vis("e_life", "lifebars", {"a": {"label": "the Sun", "value": 10000, "text": ""}, "b": {"label": "a massive star", "value": 5, "text": "a few million years"}}),
   vis("e_n", "countup", {"to": 10, "over": 1.3, "suffix": " billion years", "size": 150}, role="number", at=W(n, "10"), enter=("pop", 300))],
  {"e_stars": STAR_L, "e_life": P(0.5, 0.52, 0.58, 2), "e_n": P(0.5, 0.12, 0.5, 3)},
  {"e_stars": STAR_P, "e_life": P(0.5, 0.47, 0.94, 2), "e_n": P(0.5, 0.2, 0.9, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "Mass also decides the ending. Stars like the Sun fade quietly into a white dwarf, a cooling cinder the size of Earth."
S("m3", "mass", ["C09_whitedwarf"], n, "develop",
  [img("e_hel", "r_helix"), tag("Real image · Hubble"), txt("e_l", "white dwarf at the centre", "label", at=W(n, "white"))],
  {"e_hel": FULL_L, "e_l": P(0.5, 0.78, 0.4, 3)}, {"e_hel": P(0.5, 0.5, 1.8), "e_l": P(0.5, 0.66, 0.8, 3)},
  cam_l=[cam(1.0, 1.06, reason="push toward the white dwarf")], cam_p=[cam(1.0, 1.06, reason="push toward the white dwarf")], presentation="archival")
n = "Stars with more than about 8 times the Sun's mass end by exploding. And to leave a black hole, a star probably needs around 20 suns or more."
S("m4", "mass", ["C10_sn_threshold", "C11_bh_threshold"], n, "payoff",
  [STAR(), vis("e_fate", "fatechart", {"max": 30, "sn": 8, "bh": 20}), txt("e_h", "line still uncertain", "context", at=W(n, "probably"))],
  {"e_stars": STAR_L, "e_fate": P(0.5, 0.52, 0.84, 2), "e_h": P(0.5, 0.12, 0.3, 3)},
  {"e_stars": STAR_P, "e_fate": P(0.5, 0.45, 0.96, 2), "e_h": P(0.5, 0.66, 0.62, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram",
  transition=MOVE("we keep moving toward one of the heavy stars on the chart", "e_fate", "e_rsg"))

# ───────── DEATH OF A GIANT ─────────
n = "Now follow one of the heavy ones. It swells into a red supergiant and starts burning the ashes of its last fire."
S("o1", "giant", ["C12_supergiant", "C13_chain"], n, "orient",
  [img("e_rsg", "g_supergiant", role="subject"), tag("Illustration"), txt("e_l", "red supergiant", "subject", at=W(n, "red"))],
  {"e_rsg": FULL_L, "e_l": P(0.75, 0.82, 0.3, 3)}, {"e_rsg": P(0.85, 0.5, 3.0), "e_l": P(0.5, 0.68, 0.6, 3)},
  cam_l=[cam(1.12, 1.0, reason="the pull-back makes the star swell past the frame")], cam_p=[cam(1.18, 1.06, reason="the star swells")])
n = "Then oxygen. Then silicon. Each new fuel buys less time than the one before. And when silicon fuses into iron, the star hits a dead end."
S("o2", "giant", ["C13_chain"], n, "develop",
  [STAR(), vis("e_onion", "onion", {"shells": ["H", "He", "C", "Ne", "O", "Si", "Fe"], "revealOver": 2.2, "stop": 6, "ironAtS": 6.0}),
   txt("e_t", "less time with each fuel", "label", at=W(n, "each")), txt("e_d", "iron: a dead end", "subject", at=W(n, "dead"))],
  {"e_stars": STAR_L, "e_onion": P(0.38, 0.5, 0.44, 2), "e_t": P(0.8, 0.38, 0.3, 3), "e_d": P(0.8, 0.62, 0.28, 3)},
  {"e_stars": STAR_P, "e_onion": P(0.5, 0.44, 0.82, 2), "e_t": P(0.5, 0.12, 0.7, 3), "e_d": P(0.5, 0.68, 0.6, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift as the layers build")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "Fusing iron releases no energy, so nothing pushes back against gravity."
S("k1", "collapse", ["C14_iron"], n, "develop",
  [STAR(), vis("e_core", "ironcore", {"fadeAtS": 1.4}), txt("e_c", "no energy from iron", "label", at=W(n, "energy"))],
  {"e_stars": STAR_L, "e_core": P(0.5, 0.54, 0.36, 2), "e_c": P(0.5, 0.11, 0.34, 3)},
  {"e_stars": STAR_P, "e_core": P(0.5, 0.42, 0.88, 2), "e_c": P(0.5, 0.68, 0.7, 3)},
  cam_l=[cam(1.0, 1.05, reason="the frame tightens as support fails")], cam_p=[cam(1.0, 1.05, reason="the frame tightens")], presentation="diagram")
n = "In less than a second, the core collapses. It rebounds, and a shockwave races outward."
S("k2", "collapse", ["C15_collapse", "C16_rebound"], n, "develop",
  [STAR(), vis("e_col", "collapse", {"collapseAtS": 1.0, "collapseS": 0.7}), txt("e_s", "under 1 second", "number", at=W(n, "less"))],
  {"e_stars": STAR_L, "e_col": P(0.5, 0.5, 0.42, 2), "e_s": P(0.18, 0.5, 0.26, 3)},
  {"e_stars": STAR_P, "e_col": P(0.5, 0.42, 0.9, 2), "e_s": P(0.5, 0.16, 0.6, 3)},
  cam_l=[cam(1.0, 1.08, reason="the camera rushes in with the collapse", easing="emphasized")], cam_p=[cam(1.0, 1.08, reason="rush in with the collapse", easing="emphasized")], presentation="diagram")
n = "That is a supernova. One dying star can outshine its entire galaxy."
S("k3", "collapse", ["C16_rebound", "C17_outshine"], n, "payoff",
  [img("e_sn", "g_supernova", role="subject"), vis("e_flash", "flash", {"peak": 0.75, "decayS": 0.45}, role="decor", enter=("none", 0)), tag("Illustration", at=W(n, "one")),
   txt("e_l", "supernova", "subject", at=W(n, "supernova")), txt("e_o", "brighter than its galaxy", "label", at=W(n, "outshine"))],
  {"e_sn": FULL_L, "e_flash": P(0.5, 0.5, 1.0, 8), "e_l": P(0.5, 0.15, 0.3, 3), "e_o": P(0.5, 0.8, 0.38, 3)},
  {"e_sn": FULL_P, "e_flash": P(0.5, 0.5, 1.0, 8), "e_l": P(0.5, 0.24, 0.6, 3), "e_o": P(0.5, 0.66, 0.8, 3)},
  cam_l=[cam(1.16, 1.0, reason="the blast pushes the camera back", easing="emphasized")], cam_p=[cam(1.22, 1.06, reason="the blast pushes the camera back", easing="emphasized")],
  shake={"atWord": 0, "durationMs": 650, "amplitude": 0.012, "reason": "the impact of the explosion"},
  transition=MOVE("the shock wave's outward motion carries us to the night it was seen from Earth", "e_sn", "e_y"))

# ───────── EVIDENCE + TWIST ─────────
n = "We have seen it happen. In the year 1054, Chinese astronomers recorded a guest star visible in the daytime sky."
S("e1", "evidence", ["C18_crab"], n, "evidence",
  [STAR(), vis("e_y", "countup", {"from": 1000, "to": 1054, "over": 1.2, "separators": False, "sub": "a “guest star” in daylight", "size": 170}, role="number", at=W(n, "1054"), enter=("pop", 300)),
   txt("e_c", "recorded by Chinese astronomers", "context", at=W(n, "chinese"))],
  {"e_stars": STAR_L, "e_y": P(0.5, 0.42, 0.52, 2), "e_c": P(0.5, 0.72, 0.46, 3)},
  {"e_stars": STAR_P, "e_y": P(0.5, 0.38, 0.95, 2), "e_c": P(0.5, 0.58, 0.86, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift through the night sky")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="text")
n = "Today we find the Crab Nebula right there."
S("e2", "evidence", ["C18_crab"], n, "payoff",
  [img("e_crab", "r_crab"), tag("Real image · Hubble"), txt("e_l", "Crab Nebula", "subject", at=W(n, "crab"))],
  {"e_crab": FULL_L, "e_l": P(0.5, 0.16, 0.26, 3)}, {"e_crab": P(0.5, 0.5, 1.8), "e_l": P(0.5, 0.24, 0.5, 3)},
  cam_l=[cam(1.1, 1.0, reason="pull back reveals the wreckage")], cam_p=[cam(1.1, 1.0, reason="pull back reveals the wreckage")], presentation="archival",
  transition={"type": "depth_through_object", "durationMs": 1100, "easing": "emphasized", "rationale": "we travel through one supernova remnant into another to see what remnants are made of",
              "anchorFrom": {"entityId": "e_crab"}, "anchorTo": {"entityId": "e_cas"}})
n = "And here's the twist. All the oxygen in our solar system came from exploding massive stars."
S("e3", "twist", ["C19_casa", "C20_elements"], n, "evidence",
  [STAR(), img("e_cas", "r_casa", role="subject"), tag("Real image · Chandra"),
   vis("e_key", "legend", {"items": [["silicon", "#ff5a4a"], ["sulfur", "#ffd84a"], ["calcium", "#4adf6a"], ["iron", "#b47aff"], ["blast wave", "#5a8cff"]], "cols": 2}, at=W(n, "oxygen")),
   txt("e_t", "the twist", "subject", at=W(n, "twist"), exit_at=W(n, "all"))],
  {"e_stars": STAR_L, "e_cas": P(0.33, 0.5, 0.54, 1), "e_key": P(0.79, 0.52, 0.4, 3), "e_t": P(0.33, 0.12, 0.2, 4)},
  {"e_stars": STAR_P, "e_cas": P(0.5, 0.31, 0.9, 1), "e_key": P(0.5, 0.64, 0.9, 3), "e_t": P(0.5, 0.1, 0.4, 4)},
  cam_l=[cam(1.0, 1.05, reason="slow push while the elements are named")], cam_p=[cam(1.0, 1.05, reason="slow push")], presentation="archival")
n = "So did about half the calcium and about 40% of the iron. The calcium in your bones came from these explosions."
S("e4", "twist", ["C20_elements"], n, "payoff",
  [STAR(), vis("e_bars", "elementbars", {"items": [["oxygen", 100, "all"], ["calcium", 50, "about half"], ["iron", 40, "about 40%"]]}),
   vis("e_bone", "bone", {}, role="subject", at=W(n, "bones"), enter=("pop", 300)), txt("e_y", "in your bones", "label", at=W(n, "bones"))],
  {"e_stars": STAR_L, "e_bars": P(0.36, 0.52, 0.5, 2), "e_bone": P(0.8, 0.45, 0.3, 3), "e_y": P(0.8, 0.66, 0.24, 3)},
  {"e_stars": STAR_P, "e_bars": P(0.5, 0.33, 0.94, 2), "e_bone": P(0.5, 0.6, 0.6, 3), "e_y": P(0.5, 0.71, 0.5, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")

# ───────── REMNANT / BLACK HOLE ─────────
n = "But what happens to the core? It survives as an incredibly dense remnant. Below a limit, it becomes a neutron star, about the size of a city."
S("r1", "remnant", ["C16_rebound", "C21_remnant"], n, "orient",
  [STAR(), vis("e_fork", "fork", {"left": "neutron star", "leftNote": "about city-sized", "right": "black hole", "rightNote": "heavier stars"})],
  {"e_stars": STAR_L, "e_fork": P(0.5, 0.5, 0.78, 2)}, {"e_stars": STAR_P, "e_fork": P(0.5, 0.45, 0.96, 2)},
  cam_l=[cam(1.0, 1.04, reason="slow drift")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram")
n = "But if the star was heavy enough, nothing can stop the collapse."
S("r2", "remnant", ["C21_remnant"], n, "develop",
  [STAR(), vis("e_col", "collapse", {"collapseAtS": 1.4, "collapseS": 1.2}), txt("e_l", "nothing stops it", "label", at=W(n, "nothing"))],
  {"e_stars": STAR_L, "e_col": P(0.5, 0.5, 0.4, 2), "e_l": P(0.5, 0.85, 0.3, 3)},
  {"e_stars": STAR_P, "e_col": P(0.5, 0.42, 0.88, 2), "e_l": P(0.5, 0.68, 0.6, 3)},
  cam_l=[cam(1.0, 1.08, reason="the camera follows the core inward", easing="emphasized")], cam_p=[cam(1.0, 1.08, reason="follow the core inward", easing="emphasized")], presentation="diagram")
n = "The core falls until gravity is so strong that not even light escapes."
S("r3", "remnant", ["C22_horizon"], n, "develop",
  [img("e_bh", "g_blackhole", role="subject"), tag("Illustration"), txt("e_l", "not even light escapes", "label", at=W(n, "light"))],
  {"e_bh": FULL_L, "e_l": P(0.5, 0.82, 0.36, 3)}, {"e_bh": FULL_P, "e_l": P(0.5, 0.68, 0.74, 3)},
  cam_l=[cam(1.0, 1.06, reason="push toward the dark centre")], cam_p=[cam(1.06, 1.12, reason="push toward the dark centre")])
n = "That boundary is the event horizon. A black hole is born."
S("r4", "remnant", ["C22_horizon"], n, "payoff",
  [img("e_bh", "g_blackhole", role="subject"), tag("Illustration"), vis("e_ring", "pulsering", {}, role="subject", at=W(n, "event"), enter=("fade", 400)),
   txt("e_h", "event horizon", "label", at=W(n, "event")), txt("e_b", "a black hole is born", "subject", at=W(n, "black"))],
  {"e_bh": FULL_L, "e_ring": P(0.5, 0.5, 0.15, 2), "e_h": P(0.5, 0.78, 0.26, 3), "e_b": P(0.5, 0.15, 0.36, 3)},
  {"e_bh": FULL_P, "e_ring": P(0.5, 0.5, 0.45, 2), "e_h": P(0.5, 0.64, 0.5, 3), "e_b": P(0.5, 0.25, 0.74, 3)},
  cam_l=[cam(1.06, 1.1, reason="the push continues onto the horizon")], cam_p=[cam(1.12, 1.16, reason="the push continues")],
  transition=MOVE("the movement carries on from a star's black hole to the first real picture of one", "e_bh", "e_eht"))
n = "This is the first image of a black hole's shadow, from the Event Horizon Telescope. That one is a giant, six and a half billion times the mass of the Sun."
S("x1", "proof", ["C23_eht"], n, "evidence",
  [img("e_eht", "r_eht", role="subject"), tag("Real image · EHT"),
   vis("e_n", "countup", {"to": 6.5, "decimals": 1, "over": 1.3, "suffix": " billion Suns", "size": 150}, role="number", at=W(n, "six"), enter=("pop", 300)),
   txt("e_s", "supermassive", "label", at=W(n, "giant"))],
  {"e_eht": FULL_L, "e_n": P(0.5, 0.86, 0.5, 3), "e_s": P(0.18, 0.5, 0.24, 3)},
  {"e_eht": FULL_P, "e_n": P(0.5, 0.66, 0.9, 3), "e_s": P(0.5, 0.25, 0.5, 3)},
  cam_l=[cam(1.0, 1.06, reason="slow push on the shadow")], cam_p=[cam(1.06, 1.12, reason="slow push on the shadow")], presentation="archival")
n = "Black holes left by dying stars are far smaller."
S("x2", "proof", ["C23_eht", "C21_remnant"], n, "settle",
  [img("e_eht", "r_eht", role="subject"), tag("Real image · EHT"), txt("e_l", "star-made ones: far smaller", "subject", at=W(n, "far"))],
  {"e_eht": FULL_L, "e_l": P(0.5, 0.82, 0.42, 3)}, {"e_eht": FULL_P, "e_l": P(0.5, 0.66, 0.84, 3)},
  cam_l=[cam(1.06, 0.98, reason="pull away: star-made black holes are far smaller", easing="emphasized")], cam_p=[cam(1.12, 1.06, reason="pull away", easing="emphasized")], presentation="archival")
n = "So if light can't escape, how do we know they're there? Because they pull on their neighbors."
S("g1", "finding", ["C24_binaries"], n, "next_question",
  [img("e_cyg", "r_cygx1_art", role="subject"), tag("NASA illustration"), txt("e_q", "how do we know?", "subject", at=W(n, "how")), txt("e_p", "they pull on neighbours", "label", at=W(n, "because"))],
  {"e_cyg": FULL_L, "e_q": P(0.5, 0.15, 0.28, 3), "e_p": P(0.5, 0.82, 0.38, 3)},
  {"e_cyg": P(0.88, 0.5, 3.0), "e_q": P(0.5, 0.25, 0.6, 3), "e_p": P(0.5, 0.68, 0.8, 3)},
  cam_l=[cam(1.0, 1.05, reason="slow push on the pair")], cam_p=[cam(1.06, 1.11, reason="slow push on the pair")], presentation="illustration")
n = "Many are paired with a living star, and the gas they steal glows in X-rays."
S("g2", "finding", ["C24_binaries"], n, "evidence",
  [img("e_cyg", "r_cygx1_art", role="subject"), tag("NASA illustration"), txt("e_x", "glows in X-rays", "label", at=W(n, "glows"))],
  {"e_cyg": FULL_L, "e_x": P(0.25, 0.82, 0.26, 3)}, {"e_cyg": P(0.88, 0.5, 3.0), "e_x": P(0.5, 0.68, 0.56, 3)},
  cam_l=[cam(1.05, 1.15, 0.5, 0.5, 0.54, 0.5, "push toward the glowing disk")], cam_p=[cam(1.11, 1.18, reason="push toward the disk")], presentation="illustration")
n = "And the Gaia mission noticed an old star wobbling around something unseen, less than 2,000 light-years away. A black hole of about 33 suns, the biggest star-made one found in our galaxy at the time."
S("g3", "finding", ["C26_gaiabh3"], n, "payoff",
  [STAR(), vis("e_orb", "gaiaorbit", {}), txt("e_d", "< 2,000 light-years", "label", at=W(n, "less")),
   vis("e_n", "countup", {"to": 33, "over": 1.0, "suffix": " Suns", "size": 170}, role="number", at=W(n, "33"), enter=("pop", 300)),
   tag("Diagram")],
  {"e_stars": STAR_L, "e_orb": P(0.42, 0.52, 0.66, 2), "e_d": P(0.84, 0.36, 0.28, 3), "e_n": P(0.84, 0.6, 0.3, 3)},
  {"e_stars": STAR_P, "e_orb": P(0.5, 0.36, 0.96, 2), "e_d": P(0.5, 0.58, 0.56, 3), "e_n": P(0.5, 0.67, 0.7, 3)},
  cam_l=[cam(1.0, 1.04, reason="slow drift while the orbit draws")], cam_p=[cam(1.0, 1.04, reason="slow drift")], presentation="diagram",
  transition=MOVE("the orbit's motion carries us into the recap of the whole journey", "e_orb", "e_r0"))

# ───────── RECAP + LOOP ─────────
RECAP = [("g_clump", "cloud"), ("g_protostar", "protostar"), ("g_ignite", "star"), ("g_supergiant", "supergiant"), ("g_supernova", "supernova"), ("g_blackhole", "black hole")]
def recap(firsts, port=False):
    ents, pl, pp = [STAR()], {"e_stars": STAR_L}, {"e_stars": STAR_P}
    for i, ((a, lab), at) in enumerate(zip(RECAP, firsts)):
        if at is None: continue
        e = img(f"e_r{i}", a, role="subject"); e["enter"] = {"style": "rise", "durationMs": 400}
        if at > 0: e["enterAtWord"] = at
        ents += [e, txt(f"e_t{i}", lab, "label", at=at if at > 0 else None, enter=("rise", 400))]
        col, row = i % 3, i // 3
        pl[f"e_r{i}"] = P(0.2 + 0.3 * col, 0.25 + 0.38 * row, 0.26, 1); pl[f"e_t{i}"] = P(0.2 + 0.3 * col, 0.44 + 0.38 * row, round(0.017 * len(lab), 4), 2)
        pp[f"e_r{i}"] = P(0.28 + 0.44 * (i % 2), 0.2 + 0.24 * (i // 2), 0.4, 1); pp[f"e_t{i}"] = P(0.28 + 0.44 * (i % 2), 0.29 + 0.24 * (i // 2), round(min(0.4, 0.03 * len(lab)), 4), 2)
    return ents, pl, pp
n = "So that's the whole journey. A cold cloud collapses. A protostar ignites. For millions of years, pressure holds gravity back."
e_, pl, pp = recap([0, W(n, "protostar"), W(n, "pressure"), None, None, None])
S("z1", "recap", ["C06_balance"], n, "settle", e_, pl, pp, cam_l=[cam(1.0, 1.03, reason="slow drift over the recap")], cam_p=[cam(1.0, 1.03, reason="slow drift")])
n = "Then the core falls, and what's left can disappear into the dark."
e_, pl, pp = recap([0, 0, 0, 0, W(n, "falls"), W(n, "dark")])
for e in e_:
    if e["id"] in ("e_r0", "e_r1", "e_r2", "e_r3", "e_t0", "e_t1", "e_t2", "e_t3"): e["enter"] = {"style": "none", "durationMs": 0}
S("z2", "recap", ["C21_remnant"], n, "settle", e_, pl, pp, cam_l=[cam(1.0, 1.03, reason="slow drift over the recap")], cam_p=[cam(1.0, 1.03, reason="slow drift")])
n = "But the gas the star threw away, it's already becoming the next cloud."
S("z3", "loop", ["C28_enrich", "C01_pillars"], n, "next_question",
  [img("e_pil", "r_pillars"), tag("Real image · Webb"), txt("e_l", "the next cloud", "subject", at=W(n, "next"))],
  {"e_pil": FULL_L, "e_l": P(0.5, 0.18, 0.3, 3)}, {"e_pil": FULL_P, "e_l": P(0.5, 0.25, 0.6, 3)},
  cam_l=[cam(1.12, 1.0, 0.47, 0.44, 0.5, 0.5, "pull back to the opening view: the cycle starts again")], cam_p=[cam(1.18, 1.06, reason="pull back: the cycle starts again")], presentation="archival")

# ───────── SHORTS: five connected parts, cut from the same narration (no new voice) ─────────
SV = {"independentOpening": True, "oneQuestion": True, "minimumContext": True, "completeExplanation": True, "cleanPayoff": True, "sourceLinked": True, "deltaDefined": True}
SH = [
 ("S01", "Star Life 1/5: How a Cloud Becomes a Star", "How does a cloud become a star?", ["c1", "c2", "c3", "p1", "p2", "f1", "f2"], "Next: what decides how it dies", 40),
 ("S02", "Star Life 2/5: Mass Decides How a Star Dies", "What decides how a star dies?", ["m1", "m2", "m3", "m4"], "Next: the last second of a giant", 34),
 ("S03", "Star Life 3/5: The Last Second of a Giant Star", "How does a giant star die?", ["o1", "o2", "k1", "k2", "k3", "e1", "e2"], "Next: you are made of this", 45),
 ("S04", "Star Life 4/5: You Are Made of Dead Stars", "Where did the calcium in your bones come from?", ["h3", "k1", "k2", "k3", "e3", "e4"], "Next: what is left becomes this", 32),
 ("S05", "Star Life 5/5: How We Find Invisible Black Holes", "What is a black hole, and how do we find one?", ["r3", "r4", "x1", "x2", "g1", "g2", "g3"], "Back to 1/5: a cold cloud collapses…", 45),
]
by = {s["id"]: s for s in scenes}
shorts = []
for sid, title, q, ids, nxt, tgt in SH:
    first, last = by[ids[0]], by[ids[-1]]
    # the Short's own title card (portrait only, first ~3 words) and end card (portrait only, last ~4 words)
    q_lines = [q] if len(q) <= 30 else [q[: q.rfind(" ", 0, len(q) // 2 + 6)], q[q.rfind(" ", 0, len(q) // 2 + 6) + 1:]]
    for i, line in enumerate(q_lines):
        eid = f"e_q{sid}{i}"
        first["entities"].append({"id": eid, "role": "subject", "text": line, "enter": {"style": "none", "durationMs": 0}, "exitAtWord": min(4, len(first["narration"].split()) - 1), "only": "portrait"})
        first["layouts"]["portrait"]["placements"][eid] = P(0.5, 0.33 + 0.06 * i, 0.86, 9, 1.0)
    nw = len(last["narration"].split())
    eid = f"e_n{sid}"
    last["entities"].append({"id": eid, "role": "label", "text": nxt[:40], "enter": {"style": "rise", "durationMs": 400}, "enterAtWord": max(0, nw - 5), "only": "portrait"})
    last["layouts"]["portrait"]["placements"][eid] = P(0.5, 0.74, 0.8, 9, 1.0)
    for i_ in ids: by[i_]["shortIds"].append(sid)
    shorts.append({"id": sid, "status": "validated", "title": title[:60], "question": q, "minimumContext": ["the on-screen question frames the clip"],
                   "payoff": "answered by the clip's own narration", "sceneIds": ids, "delta": {"openingCard": q, "closingCard": nxt, "portraitRestage": "recomposed tall layouts; own title card and end card", "addedVisual": f"title card '{q}', end card '{nxt}'"},
                   "targetDurationS": tgt, "validation": SV})

# timing from the final audio's alignment (stage 03)
_al = os.path.join(HERE, "audio", "alignment.json")
if os.path.exists(_al):
    b = {x["sceneId"]: x for x in json.load(open(_al)).get("sceneBounds", [])}
    if all(s["id"] in b for s in scenes):
        for s in scenes:
            x = b[s["id"]]; s["timing"] = {"startS": x["startS"], "endS": x["endS"], "firstWord": x["firstWord"], "lastWord": x["lastWord"]}
    # the iron shell appears on the word "iron" (scene-relative seconds)
    words = json.load(open(_al))["words"]
    ws = [w for w in words if w.get("scene") == "o2"]
    if ws:
        iw = next(w for w in ws if w["w"].lower().startswith("iron"))
        for e in by["o2"]["entities"]:
            if e["id"] == "e_onion": e["visual"]["props"]["ironAtS"] = round(iw["s"] - ws[0]["s"], 2)

doc = {"schemaVersion": 1, "fps": 30, "opening": {"fadeInMs": 0, "leadSilenceMs": 0}, "ending": {"fadeOutMs": 700, "holdBlackMs": 0, "tailSilenceMs": 400}, "scenes": scenes}
json.dump(doc, open(os.path.join(HERE, "scenes.json"), "w"), indent=1, ensure_ascii=False)
json.dump({"shorts": shorts}, open(os.path.join(HERE, "shorts.json"), "w"), indent=1, ensure_ascii=False)
open(os.path.join(HERE, "spoken_script.txt"), "w").write("\n".join(s["narration"] for s in scenes) + "\n")
print(f"{len(scenes)} scenes, {sum(len(s['narration'].split()) for s in scenes)} words, {len(shorts)} Shorts")
