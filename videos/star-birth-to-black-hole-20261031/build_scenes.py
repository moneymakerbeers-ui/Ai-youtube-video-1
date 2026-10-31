#!/usr/bin/env python3
"""build_scenes.py — this video's scene source of truth (narration, visuals, layouts, Shorts) → scenes.json, shorts.json, spoken_script.txt.
Run: python3 videos/star-birth-to-black-hole-20261031/build_scenes.py [--no-assets]
--no-assets writes entities with `need` only (stage 01, before assets/manifest.json exists)."""
import json, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
NO_ASSETS = "--no-assets" in sys.argv

# ---------- helpers ----------
def V(intent, emotion="neutral-clear", intensity=0, pace="steady", emph=(), pb=0, pa=0, notes=None, pron=()):
    v = {"intent": intent, "emotion": emotion, "intensity": intensity, "pace": pace, "emphasisWords": list(emph), "pauseBeforeMs": pb, "pauseAfterMs": pa}
    if notes: v["deliveryNotes"] = notes
    if pron: v["pronunciation"] = [{"word": w, "say": s} for w, s in pron]
    return v

def img(eid, asset, need, role="backdrop", enter=("none", 0)):  # plates appear with the cut (a fade-in from the dark ground reads as black frames)
    e = {"id": eid, "role": role, "need": need, "enter": {"style": enter[0], "durationMs": enter[1]}}
    if not NO_ASSETS: e["assetId"] = asset
    return e

def vis(eid, comp, props, need, role="diagram", enter=("fade", 500), at=None):
    e = {"id": eid, "role": role, "need": need, "enter": {"style": enter[0], "durationMs": enter[1]}}
    if not NO_ASSETS: e["visual"] = {"component": comp, "props": props}
    if at is not None: e["enterAtWord"] = at
    return e

def txt(eid, text, role="label", at=None, exit_at=None, enter=("rise", 450)):
    e = {"id": eid, "role": role, "text": text, "enter": {"style": enter[0], "durationMs": enter[1]}}
    if at is not None: e["enterAtWord"] = at
    if exit_at is not None: e["exitAtWord"] = exit_at
    return e

def P(x, y, w, z=0, depth=0.0):
    return {"x": x, "y": y, "w": w, "z": z, "depth": depth}

def cam(fx, fy, fs, tx, ty, ts, reason, easing="soft"):
    return {"from": {"x": fx, "y": fy, "scale": fs}, "to": {"x": tx, "y": ty, "scale": ts}, "easing": easing, "reason": reason}

FULL_L = P(0.5, 0.5, 1.0)            # 16:9 image filling the landscape frame
FULL_P = P(0.5, 0.5, 3.0)           # 16:9 image covering the portrait frame (height-filling; sides cropped, recomposed by x)
TAG_L = P(0.845, 0.07, 0.26, z=5)    # small provenance tag, top right (landscape)
TAG_P = P(0.5, 0.105, 0.42, z=5)     # provenance tag, top centre below the portrait UI margin
STAR_L = P(0.5, 0.5, 1.0, z=-1)
STAR_P = P(0.5, 0.5, 1.0, z=-1)

def starfield(eid="e_stars"):
    return vis(eid, "starfield", {"seed": 7}, "a quiet deep-space star background", role="backdrop", enter=("fade", 400))

scenes = []
def S(id, section, claims, narration, intent, beat, presentation, entities, land, port=None, voice=None, transition=None, intensity=1, signature=None, qa=(), look=None, hold_l=None, hold_p=None, cam_l=(), cam_p=()):
    sc = {"id": id, "section": section, "claimIds": list(claims), "narration": narration, "intent": intent, "retentionBeat": beat,
          "presentation": presentation, "visualIntensity": intensity, "transition": transition or {"type": "cut"},
          "voice": voice or V("say it plainly"), "entities": entities,
          "layouts": {"landscape": {"placements": land, "camera": list(cam_l)}}, "shortIds": [], "assetIds": [], "qaRisk": list(qa)}
    if hold_l: sc["layouts"]["landscape"]["hold"] = {"reason": hold_l}
    if port is not None:
        sc["layouts"]["portrait"] = {"placements": port, "camera": list(cam_p)}
        if hold_p: sc["layouts"]["portrait"]["hold"] = {"reason": hold_p}
    if signature: sc["signature"] = signature
    if look: sc["look"] = look
    scenes.append(sc)
    return sc

REAL_WEBB = "Real image · Webb"
ILLU = "Illustration"

# ---------- 1 open ----------
S("s01", "open", ["C01_pillars"],
  "This is a real photograph of a place where stars are being born right now. The Pillars of Creation, seen by the James Webb Space Telescope.",
  "the viewer sees and names a real stellar nursery in the first frame", "promise", "archival",
  [img("e_pil", "r_pillars", "real Webb photograph of the Pillars of Creation"), txt("e_tag", REAL_WEBB, "context", at=3)],
  {"e_pil": FULL_L, "e_tag": TAG_L}, {"e_pil": P(0.5, 0.5, 3.0), "e_tag": TAG_P},
  voice=V("open with a concrete, true image", "quiet-wonder", 1, "steady", ["real", "right now"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.47, 1.08, "slow push lets the eye settle on the pillars where stars form")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.47, 1.06, "slow push toward the pillar tips in the tall frame")])
S("s02", "open", ["C01_pillars", "C11_bh_threshold"],
  "Inside these columns of cold gas and dust, new stars are forming. Give one of them enough mass, and its life could end as a black hole.",
  "connect the nursery to the ending the title promises", "promise", "archival",
  [img("e_pil", "r_pillars", "the same Webb pillars, closer on one tip"), txt("e_tag", REAL_WEBB, "context")],
  {"e_pil": FULL_L, "e_tag": TAG_L}, {"e_pil": P(0.5, 0.5, 3.0), "e_tag": TAG_P},
  voice=V("name the destination of the journey", "curious", 1, "steady", ["enough mass", "black hole"]),
  cam_l=[cam(0.5, 0.47, 1.08, 0.48, 0.44, 1.2, "continues the push into one pillar tip, where a new star could be hiding")],
  cam_p=[cam(0.5, 0.47, 1.06, 0.48, 0.42, 1.25, "continues the push into one pillar tip")],
  transition={"type": "dissolve", "durationMs": 600})
S("s03", "open", ["C06_balance"],
  "So how does a soft cloud of dust become the darkest object in the universe? The answer is a tug-of-war that lasts millions of years. And for the heaviest stars, gravity wins completely.",
  "state the one question and the thread (gravity vs pressure)", "next_question", "comparison",
  [starfield(), img("e_a", "r_pillars", "small real image of the pillars: the start", role="subject", enter=("rise", 600)),
   img("e_b", "g_blackhole", "small illustration of a black hole: the end", role="subject", enter=("rise", 600)),
   txt("e_la", "Start: a cloud", at=1), txt("e_lb", "End: a black hole", at=11), txt("e_ill", ILLU, "context", at=11),
   txt("e_q", "Gravity vs. pressure", "subject", at=17)],
  {"e_stars": STAR_L, "e_a": P(0.27, 0.42, 0.38, 1), "e_b": P(0.73, 0.42, 0.38, 1), "e_la": P(0.27, 0.72, 0.3, 2), "e_lb": P(0.73, 0.72, 0.32, 2),
   "e_ill": P(0.73, 0.2, 0.16, 3), "e_q": P(0.5, 0.13, 0.5, 3)},
  {"e_stars": STAR_P, "e_a": P(0.5, 0.26, 0.86, 1), "e_b": P(0.5, 0.6, 0.86, 1), "e_la": P(0.5, 0.425, 0.7, 2), "e_lb": P(0.5, 0.765, 0.7, 2),
   "e_ill": P(0.5, 0.47, 0.4, 3), "e_q": P(0.5, 0.135, 0.8, 3)},
  voice=V("hand over the core question, then the thread", "curious", 1, "steady", ["darkest", "tug-of-war", "completely"], pa=300),
  hold_l="the two ends of the journey sit side by side while the question is asked",
  hold_p="the two ends of the journey sit stacked while the question is asked", qa=["text_safe_area"])

# ---------- 2 cloud ----------
S("s04", "cloud", ["C02_cloud"],
  "It starts in a molecular cloud. These clouds can hold up to ten million times the mass of the Sun, and stretch hundreds of light-years across.",
  "orient: the raw material is enormous and real", "orient", "archival",
  [img("e_car", "r_carina", "real Webb image of a giant gas-and-dust cloud edge (Cosmic Cliffs, Carina)"), txt("e_tag", REAL_WEBB, "context"),
   txt("e_n", "up to 10 million Suns of gas", "number", at=8)],
  {"e_car": FULL_L, "e_tag": TAG_L, "e_n": P(0.5, 0.83, 0.56, 3)}, {"e_car": P(0.62, 0.5, 3.0), "e_tag": TAG_P, "e_n": P(0.5, 0.7, 0.86, 3)},
  voice=V("set the scale", "warm-explanatory", 0, "steady", ["ten million", "hundreds"]),
  cam_l=[cam(0.5, 0.5, 1.04, 0.56, 0.5, 1.04, "a slow pan across the cloud shows how wide it is")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.56, 0.5, 1.0, "a slow pan across the cloud in the tall frame")])
S("s05", "cloud", ["C02_cloud"],
  "They are cold, and cold gas clumps together. Some clumps collide, or gather more matter, and their gravity grows stronger.",
  "develop: how clumps form and grow", "develop", "archival",
  [img("e_car", "r_carina", "the same cloud, closer on dense dark knots"), txt("e_tag", REAL_WEBB, "context"), txt("e_l", "cold gas clumps", "label", at=5)],
  {"e_car": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.84, 0.36, 3)}, {"e_car": P(0.62, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.7, 0.7, 3)},
  voice=V("explain step by step", "warm-explanatory", 0),
  cam_l=[cam(0.56, 0.5, 1.04, 0.59, 0.47, 1.2, "push in toward the densest knots, where clumps gather")],
  cam_p=[cam(0.56, 0.5, 1.0, 0.6, 0.46, 1.2, "push in toward the densest knots")])
S("s06", "cloud", ["C02_cloud"],
  "Eventually, gravity takes over, and one clump begins to collapse.",
  "the first turning point: collapse starts", "payoff", "illustration",
  [img("e_clump", "g_clump", "illustration: one dark dense clump inside a cloud starting to collapse, faint glow at its centre", role="subject"), txt("e_tag", ILLU, "context")],
  {"e_clump": FULL_L, "e_tag": TAG_L}, {"e_clump": P(0.5, 0.5, 3.0), "e_tag": TAG_P},
  voice=V("mark the turning point", "quiet-wonder", 1, "slower", ["collapse"], pa=200),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.12, "the camera follows the clump inward as it begins to fall in on itself")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.1, "follow the clump inward")],
  transition={"type": "nested_scale", "durationMs": 1800, "easing": "emphasized",
              "rationale": "the protostar is literally the inside of the collapsing clump: zooming into its centre shows the same object one scale down",
              "anchorFrom": {"entityId": "e_core", "x": 0.5, "y": 0.5}, "anchorTo": {"entityId": "e_proto", "x": 0.5, "y": 0.5}},
  intensity=3, signature={"before": "a whole collapsing clump in a dark cloud", "after": "the hot protostar at the clump's centre", "track": "the glowing centre of the clump"},
  qa=["morph_geometry"])
scenes[-1]["entities"].append(vis("e_core", "glowdot", {"color": "#ffcf8a"}, "the faint warm centre of the clump (anchor for the zoom)", role="subject", enter=("fade", 800)))
scenes[-1]["layouts"]["landscape"]["placements"]["e_core"] = P(0.5, 0.5, 0.12, 2)
scenes[-1]["layouts"]["portrait"]["placements"]["e_core"] = P(0.5, 0.5, 0.26, 2)

# ---------- 3 protostar ----------
S("s07", "protostar", ["C03_protostar"],
  "As the gas falls inward, it heats up. At the center, a hot, dense knot forms: a protostar. A baby star.",
  "name the new object", "develop", "illustration",
  [img("e_proto", "g_protostar", "illustration: a glowing protostar wrapped in a dusty disk and envelope, twin jets", role="subject"), txt("e_tag", ILLU, "context"),
   txt("e_l", "protostar", "label", at=13)],
  {"e_proto": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.84, 0.26, 3)}, {"e_proto": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.7, 0.5, 3)},
  voice=V("introduce the baby star", "warm-explanatory", 1, "steady", ["protostar"]),
  cam_l=[cam(0.5, 0.5, 1.12, 0.5, 0.5, 1.0, "settles back from the zoom so the whole protostar and disk read")],
  cam_p=[cam(0.5, 0.5, 1.1, 0.5, 0.5, 1.0, "settles back from the zoom")])
S("s08", "protostar", ["C03_protostar"],
  "It isn't burning anything yet. Its glow comes from the heat of its own collapse.",
  "correct a likely misconception: the glow is not fusion", "payoff", "illustration",
  [img("e_proto", "g_protostar", "same protostar illustration"), txt("e_tag", ILLU, "context"), txt("e_l", "heat from collapse, not fusion", "label", at=6)],
  {"e_proto": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.84, 0.5, 3)}, {"e_proto": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.7, 0.86, 3)},
  voice=V("gently correct", "matter-of-fact", 0, emph=["yet"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.08, "a slow push keeps attention on the glowing core")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.06, "slow push on the core")])
S("s09", "protostar", ["C04_jets"],
  "Young stars also fire jets of gas into space. In this Webb image of a nearby nursery, the red streaks are jets, launched as young stars first burst out of their dusty cocoons.",
  "real evidence of young stars", "evidence", "archival",
  [img("e_rho", "r_rhooph", "real Webb image of Rho Ophiuchi with red bipolar jets"), txt("e_tag", REAL_WEBB, "context"), txt("e_l", "red streaks = jets", "label", at=16)],
  {"e_rho": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.84, 0.34, 3)}, {"e_rho": P(0.45, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.7, 0.66, 3)},
  voice=V("show the proof", "curious", 1, emph=["jets", "red streaks"]),
  cam_l=[cam(0.5, 0.5, 1.02, 0.5, 0.45, 1.18, "drift toward the upper jets while they are named")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.52, 0.45, 1.1, "drift toward the jets")])

# ---------- 4 ignition ----------
S("s10", "ignition", ["C05_ignition"],
  "The protostar keeps gaining mass, and its core gets hotter and denser. At about fifteen million degrees, something new happens.",
  "build to the threshold", "develop", "diagram",
  [starfield(), vis("e_temp", "thermo", {"to": 15, "unit": "million °", "label": "core temperature"}, "a core-temperature readout climbing to about 15 million degrees", role="number", at=11),
   txt("e_l", "core temperature", "context", at=9)],
  {"e_stars": STAR_L, "e_temp": P(0.5, 0.52, 0.6, 2), "e_l": P(0.5, 0.15, 0.36, 2)},
  {"e_stars": STAR_P, "e_temp": P(0.5, 0.45, 0.9, 2), "e_l": P(0.5, 0.3, 0.7, 2)},
  voice=V("build anticipation without hype", "curious", 1, "steady", ["fifteen million"], pa=250),
  transition={"type": "dissolve", "durationMs": 700})
S("s11", "ignition", ["C05_ignition"],
  "Hydrogen nuclei are squeezed together so hard that they fuse into helium. That's nuclear fusion, and it releases energy. In this moment, a star is born.",
  "the payoff of part one: ignition", "payoff", "illustration",
  [img("e_ign", "g_ignite", "illustration: a newborn star igniting at the centre of its clearing cocoon", role="subject"), txt("e_tag", ILLU, "context"),
   txt("e_f", "hydrogen → helium", "label", at=8), txt("e_b", "a star is born", "subject", at=20)],
  {"e_ign": FULL_L, "e_tag": TAG_L, "e_f": P(0.5, 0.8, 0.34, 3), "e_b": P(0.5, 0.15, 0.36, 3)},
  {"e_ign": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_f": P(0.5, 0.7, 0.66, 3), "e_b": P(0.5, 0.22, 0.7, 3)},
  voice=V("deliver the birth moment", "quiet-wonder", 2, "slower", ["fuse", "born"], pb=200, pa=500),
  cam_l=[cam(0.5, 0.5, 1.12, 0.5, 0.5, 1.0, "a slow pull-back as the new star's light fills the frame")],
  cam_p=[cam(0.5, 0.5, 1.1, 0.5, 0.5, 1.0, "slow pull-back as the star ignites")])

# ---------- 5 balance ----------
S("s12", "balance", ["C06_balance"],
  "Now the real story begins. Gravity pulls every layer of the star inward. The heat from fusion pushes outward.",
  "make the central mechanism visible", "develop", "diagram",
  [starfield(), vis("e_bal", "balance", {"inAt": 0.25, "outAt": 0.75}, "a star disc with inward gravity arrows and outward pressure arrows", at=0),
   txt("e_g", "gravity: in", "label", at=6), txt("e_p", "pressure: out", "label", at=15)],
  {"e_stars": STAR_L, "e_bal": P(0.5, 0.5, 0.52, 2), "e_g": P(0.18, 0.5, 0.24, 3), "e_p": P(0.82, 0.5, 0.26, 3)},
  {"e_stars": STAR_P, "e_bal": P(0.5, 0.45, 0.95, 2), "e_g": P(0.5, 0.18, 0.56, 3), "e_p": P(0.5, 0.74, 0.6, 3)},
  voice=V("explain the tug-of-war", "warm-explanatory", 1, "steady", ["inward", "outward"]))
S("s13", "balance", ["C07_mainseq"],
  "As long as both stay balanced, the star is stable. Astronomers call this the main sequence. It's the longest phase of a star's life, and our Sun is roughly halfway through its own.",
  "name the stable phase and anchor it to the Sun", "settle", "archival",
  [img("e_sun", "r_sun", "real Solar Dynamics Observatory image of the Sun"), txt("e_tag", "Real image · SDO", "context"), txt("e_l", "main sequence", "subject", at=11),
   txt("e_h", "the Sun: about halfway", "label", at=24)],
  {"e_sun": P(0.5, 0.5, 0.48, 1), "e_tag": TAG_L, "e_l": P(0.18, 0.2, 0.3, 3), "e_h": P(0.8, 0.82, 0.34, 3)},
  {"e_sun": P(0.5, 0.47, 1.0, 1), "e_tag": TAG_P, "e_l": P(0.5, 0.2, 0.7, 3), "e_h": P(0.5, 0.76, 0.76, 3)},
  voice=V("settle", "warm-explanatory", 0, "steady", ["main sequence", "halfway"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.06, "a gentle push on the Sun while the stable phase is named")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.05, "gentle push on the Sun")])

# ---------- 6 mass ----------
S("s14", "mass", ["C08_mass_rate"],
  "How long that balance lasts depends, above all, on mass. A heavier star has to burn its fuel much faster, just to hold up its own weight.",
  "introduce the deciding variable", "develop", "diagram",
  [starfield(), vis("e_two", "twostars", {}, "a small Sun-like star and a much larger heavy star, the heavy one burning brighter", at=0),
   txt("e_m", "mass decides", "subject", at=7), txt("e_f", "heavier → burns faster", "label", at=10)],
  {"e_stars": STAR_L, "e_two": P(0.5, 0.52, 0.56, 2), "e_m": P(0.5, 0.09, 0.26, 3), "e_f": P(0.5, 0.19, 0.36, 3)},
  {"e_stars": STAR_P, "e_two": P(0.5, 0.46, 0.96, 2), "e_m": P(0.5, 0.2, 0.6, 3), "e_f": P(0.5, 0.72, 0.8, 3)},
  voice=V("make mass the key", "warm-explanatory", 1, "steady", ["mass", "faster"], pb=150))
S("s15", "mass", ["C08_mass_rate"],
  "The Sun will spend about ten billion years on the main sequence. Some massive stars live for only a few million.",
  "show the contrast with honest bars", "evidence", "diagram",
  [starfield(), vis("e_life", "lifebars", {"a": {"label": "the Sun", "value": 10000, "text": "≈10 billion years"}, "b": {"label": "a massive star", "value": 5, "text": "a few million years"}},
                    "two lifetime bars on one linear scale: the Sun ~10 billion years vs a massive star a few million", at=0)],
  {"e_stars": STAR_L, "e_life": P(0.5, 0.47, 0.6, 2)},
  {"e_stars": STAR_P, "e_life": P(0.5, 0.47, 0.94, 2)},
  voice=V("let the contrast land", "matter-of-fact", 1, "steady", ["ten billion", "few million"]))
S("s16", "mass", ["C09_whitedwarf"],
  "Mass also decides the ending. Stars like the Sun finish quietly, as a white dwarf: a cooling cinder about the size of Earth.",
  "the common, gentle ending", "develop", "archival",
  [img("e_hel", "r_helix", "real image of the Helix Nebula with its central white dwarf"), txt("e_tag", "Real image · Hubble", "context"),
   txt("e_l", "white dwarf at the centre", "label", at=13)],
  {"e_hel": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.86, 0.4, 3)}, {"e_hel": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.7, 0.8, 3)},
  voice=V("calm, gentle ending", "reflective", 1, "slower", ["quietly"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.12, "push toward the white dwarf at the centre of the shed shell")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.1, "push toward the central white dwarf")])
S("s17", "mass", ["C10_sn_threshold", "C11_bh_threshold"],
  "Stars born with more than about eight times the Sun's mass end their lives by exploding. And to leave a black hole behind, a star probably needs around twenty times the Sun's mass, or more. Exactly where that line sits is still being studied.",
  "the two thresholds on one axis, with the uncertainty visible", "payoff", "diagram",
  [starfield(), vis("e_fate", "fatechart", {"max": 30, "sn": 8, "bh": 20}, "a starting-mass axis with three zones: white dwarf, neutron star (from ~8), black hole (from ~20, fuzzy edge)", at=0),
   txt("e_h", "line still uncertain", "context", at=29)],
  {"e_stars": STAR_L, "e_fate": P(0.5, 0.48, 0.86, 2), "e_h": P(0.5, 0.12, 0.3, 3)},
  {"e_stars": STAR_P, "e_fate": P(0.5, 0.45, 0.96, 2), "e_h": P(0.5, 0.74, 0.62, 3)},
  voice=V("state thresholds, hedge honestly", "matter-of-fact", 1, "steady", ["eight", "twenty"], pa=300,
          notes="the hedge is information, not drama"))

# ---------- 7 onion ----------
S("s18", "onion", ["C12_supergiant"],
  "So let's follow one of those heavyweights. When the hydrogen in its core runs out, gravity squeezes the core, the core heats up, and the outer layers swell. The star becomes a red supergiant.",
  "begin the death sequence with one specific star", "orient", "illustration",
  [img("e_rsg", "g_supergiant", "illustration: a vast red supergiant star, mottled surface, deep space", role="subject"), txt("e_tag", ILLU, "context"),
   txt("e_l", "red supergiant", "subject", at=32)],
  {"e_rsg": FULL_L, "e_tag": TAG_L, "e_l": P(0.22, 0.85, 0.32, 3)}, {"e_rsg": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.74, 0.7, 3)},
  voice=V("turn the page to the ending", "warm-explanatory", 1, "steady", ["swell", "red supergiant"]),
  cam_l=[cam(0.5, 0.5, 1.22, 0.5, 0.5, 1.0, "the pull-back makes the star look like it is swelling past the frame")],
  cam_p=[cam(0.5, 0.5, 1.2, 0.5, 0.5, 1.0, "pull-back as the star swells")])
S("s19", "onion", ["C13_chain"],
  "Inside, it starts burning the ashes of the last fire. Helium fuses into carbon. Carbon into neon. Then oxygen, then silicon.",
  "build the fusion chain one element at a time", "develop", "diagram",
  [starfield(), vis("e_onion", "onion", {"shells": ["H", "He", "C", "Ne", "O", "Si", "Fe"], "revealOver": 9.5, "stop": 6},
                    "a cutaway of the star's core growing layers: hydrogen, helium, carbon, neon, oxygen, silicon", at=0),
   txt("e_n", "each layer: a heavier fuel", "context", at=9)],
  {"e_stars": STAR_L, "e_onion": P(0.38, 0.48, 0.44, 2), "e_n": P(0.8, 0.48, 0.3, 3)},
  {"e_stars": STAR_P, "e_onion": P(0.5, 0.42, 0.96, 2), "e_n": P(0.5, 0.74, 0.7, 3)},
  voice=V("list the chain with rhythm", "warm-explanatory", 1, "steady", ["carbon", "neon", "oxygen", "silicon"]),
  transition={"type": "dissolve", "durationMs": 500})
S("s20", "onion", ["C13_chain"],
  "Each new fuel buys the star less time than the one before. And when silicon finally fuses into iron, the star runs out of fuel in a matter of days.",
  "the clock speeds up; land on iron", "payoff", "diagram",
  [starfield(), vis("e_onion", "onion", {"shells": ["H", "He", "C", "Ne", "O", "Si", "Fe"], "revealOver": 0.01, "stop": 6, "ironAtS": 5.0},
                    "the same cutaway; an iron core appears at the centre", at=0),
   txt("e_t", "less time with each fuel", "label", at=0), txt("e_d", "iron: fuel runs out in days", "label", at=16)],
  {"e_stars": STAR_L, "e_onion": P(0.38, 0.48, 0.44, 2), "e_t": P(0.8, 0.36, 0.3, 3), "e_d": P(0.8, 0.6, 0.3, 3)},
  {"e_stars": STAR_P, "e_onion": P(0.5, 0.42, 0.96, 2), "e_t": P(0.5, 0.16, 0.7, 3), "e_d": P(0.5, 0.74, 0.8, 3)},
  voice=V("tighten", "measured-concern", 1, "steady", ["less time", "iron", "days"], pa=300))

# ---------- 8 collapse ----------
S("s21", "collapse", ["C14_iron"],
  "Iron is a dead end. Fusing iron doesn't release energy; it costs energy. So nothing is left to push back against gravity.",
  "the reason the star dies", "develop", "diagram",
  [starfield(), vis("e_core", "ironcore", {}, "the iron core alone; outward pressure arrows fade while inward gravity arrows remain", at=0),
   txt("e_c", "iron fusion costs energy", "label", at=5)],
  {"e_stars": STAR_L, "e_core": P(0.5, 0.54, 0.36, 2), "e_c": P(0.5, 0.11, 0.36, 3)},
  {"e_stars": STAR_P, "e_core": P(0.5, 0.42, 0.9, 2), "e_c": P(0.5, 0.72, 0.8, 3)},
  voice=V("state the dead end plainly", "measured-concern", 1, "steady", ["dead end", "costs"]))
S("s22", "collapse", ["C15_collapse"],
  "In less than a second, the core collapses. Its temperature soars past one hundred billion degrees.",
  "the fastest moment of the story", "develop", "diagram",
  [starfield(), vis("e_col", "collapse", {"collapseAt": 0.6, "collapseS": 0.9}, "the iron core shrinking almost instantly, with a temperature readout", at=0),
   txt("e_s", "under 1 second", "number", at=2), txt("e_t", "over 100 billion °", "number", at=9)],
  {"e_stars": STAR_L, "e_col": P(0.5, 0.47, 0.42, 2), "e_s": P(0.17, 0.5, 0.26, 3), "e_t": P(0.83, 0.5, 0.28, 3)},
  {"e_stars": STAR_P, "e_col": P(0.5, 0.42, 0.9, 2), "e_s": P(0.5, 0.17, 0.62, 3), "e_t": P(0.5, 0.74, 0.7, 3)},
  voice=V("quicken with the event", "urgent", 2, "faster", ["less than a second", "hundred billion"]),
  transition={"type": "occlusion_reveal", "durationMs": 1000, "easing": "emphasized",
              "rationale": "the shock wave really starts at the collapsed core and moves outward, so the explosion is revealed from the core's position",
              "anchorFrom": {"entityId": "e_col", "x": 0.5, "y": 0.5}, "anchorTo": {"entityId": "e_sn", "x": 0.5, "y": 0.5}},
  intensity=3, signature={"before": "a tiny collapsed iron core", "after": "the supernova blast spreading outward", "track": "the point where the core was"},
  qa=["fast_motion"])
S("s23", "collapse", ["C16_rebound"],
  "Then the core rebounds, and a shock wave races outward through the star. That is a supernova.",
  "the explosion", "payoff", "illustration",
  [img("e_sn", "g_supernova", "illustration: a supernova shock wave tearing outward through a red supergiant, no white-out", role="subject"), txt("e_tag", ILLU, "context"),
   txt("e_l", "supernova", "subject", at=14)],
  {"e_sn": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.85, 0.28, 3)}, {"e_sn": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.72, 0.56, 3)},
  voice=V("the peak", "quiet-wonder", 3, "slower", ["supernova"], pb=150, pa=400, notes="awe, not shouting"),
  cam_l=[cam(0.5, 0.5, 1.15, 0.5, 0.5, 1.0, "pull-back follows the shock wave outward")],
  cam_p=[cam(0.5, 0.5, 1.12, 0.5, 0.5, 1.0, "pull-back follows the shock wave")])
S("s24", "collapse", ["C17_outshine"],
  "For a while, this one dying star can outshine its entire galaxy, before fading over weeks or months.",
  "scale of the event, with real evidence", "evidence", "archival",
  [img("e_gal", "r_sn_hubble", "real Hubble image: a distant galaxy with a supernova as bright as its core"), txt("e_tag", "Real image · Hubble", "context"),
   txt("e_l", "one exploding star", "label", at=3)],
  {"e_gal": FULL_L, "e_tag": TAG_L, "e_l": P(0.3, 0.62, 0.3, 3)},
  {"e_gal": P(0.5, 0.45, 1.0, 1), "e_tag": TAG_P, "e_l": P(0.5, 0.72, 0.66, 3)},
  voice=V("settle after the peak", "reflective", 1, "steady", ["entire galaxy"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.08, "a gentle push so the bright point and its galaxy read together")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.06, "gentle push on the galaxy")])

# ---------- 9 evidence ----------
S("s25", "evidence", ["C18_crab"],
  "We have seen this happen. In the year ten fifty-four, Chinese astronomers recorded a 'guest star', visible in the daytime sky for nearly a month.",
  "historical evidence", "evidence", "text",
  [starfield(), txt("e_y", "1054", "number", at=6, enter=("fade", 600)), txt("e_g", "a “guest star” seen in daylight", "label", at=12),
   txt("e_m", "for nearly a month", "context", at=21)],
  {"e_stars": STAR_L, "e_y": P(0.5, 0.4, 0.3, 2), "e_g": P(0.5, 0.62, 0.46, 2), "e_m": P(0.5, 0.74, 0.3, 2)},
  {"e_stars": STAR_P, "e_y": P(0.5, 0.36, 0.6, 2), "e_g": P(0.5, 0.52, 0.86, 2), "e_m": P(0.5, 0.62, 0.6, 2)},
  voice=V("tell a true story", "warm-explanatory", 1, "steady", ["seen", "daytime"]),
  hold_l="the year and the record stay readable while the story is told",
  hold_p="the year and the record stay readable", transition={"type": "dissolve", "durationMs": 1400, "easing": "soft"})
S("s26", "evidence", ["C18_crab"],
  "Today, in that spot, we find the Crab Nebula: the expanding wreckage of that explosion, six light-years wide.",
  "the remnant of that star", "payoff", "archival",
  [img("e_crab", "r_crab", "real Hubble mosaic of the Crab Nebula"), txt("e_tag", "Real image · Hubble", "context")],
  {"e_crab": FULL_L, "e_tag": TAG_L}, {"e_crab": P(0.5, 0.5, 3.0), "e_tag": TAG_P},
  voice=V("reveal the remnant", "quiet-wonder", 2, "steady", ["Crab Nebula"]),
  cam_l=[cam(0.5, 0.5, 1.15, 0.5, 0.5, 1.0, "pull-back reveals the full width of the wreckage")],
  cam_p=[cam(0.5, 0.5, 1.12, 0.5, 0.5, 1.0, "pull-back reveals the wreckage")])
S("s27", "evidence", ["C19_casa"],
  "This is Cassiopeia A, the remains of an exploded star, mapped in X-rays. The colors show silicon, sulfur, calcium and iron, thrown out into space.",
  "elements made by stars, made visible", "evidence", "archival",
  [img("e_cas", "r_casa", "real Chandra X-ray element map of Cassiopeia A"), txt("e_tag", "Real image · Chandra", "context"),
   vis("e_key", "legend", {"items": [["silicon", "#ff5a4a"], ["sulfur", "#ffd84a"], ["calcium", "#4adf6a"], ["iron", "#b47aff"], ["blast wave", "#5a8cff"]], "cols": 2}, "a colour key naming each element", at=13)],
  {"e_cas": P(0.33, 0.5, 0.54, 1), "e_tag": TAG_L, "e_key": P(0.79, 0.52, 0.4, 3)},
  {"e_cas": P(0.5, 0.31, 0.9, 1), "e_tag": TAG_P, "e_key": P(0.5, 0.64, 0.9, 3)},
  voice=V("explain the map", "curious", 1, "steady", ["silicon", "sulfur", "calcium", "iron"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.05, "a gentle push while the colours are named")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.04, "gentle push while the colours are named")])
S("s28", "evidence", ["C20_elements"],
  "According to NASA, all the oxygen in our solar system came from exploding massive stars, along with about half the calcium and about forty percent of the iron. Some of the calcium in your bones came from these explosions.",
  "the human connection", "payoff", "diagram",
  [starfield(), vis("e_bars", "elementbars", {"items": [["oxygen", 100, "all"], ["calcium", 50, "about half"], ["iron", 40, "about 40%"]]},
                    "three bars: share of each element made by exploding massive stars", at=3),
   txt("e_t", "made by exploding massive stars", "context", at=9), txt("e_y", "in your bones", "label", at=31)],
  {"e_stars": STAR_L, "e_bars": P(0.5, 0.52, 0.54, 2), "e_t": P(0.5, 0.1, 0.44, 3), "e_y": P(0.86, 0.52, 0.2, 3)},
  {"e_stars": STAR_P, "e_bars": P(0.5, 0.45, 0.94, 2), "e_t": P(0.5, 0.17, 0.86, 3), "e_y": P(0.5, 0.74, 0.5, 3)},
  voice=V("make it personal", "warm-explanatory", 2, "steady", ["all", "your bones"], pa=400))

# ---------- 10 black hole ----------
S("s29", "blackhole", ["C16_rebound", "C21_remnant"],
  "But what about the core? It survives the blast as an incredibly dense remnant. If the star was near the lower limit, it becomes a neutron star, about the size of a city.",
  "the fork in the road", "orient", "diagram",
  [starfield(), vis("e_fork", "fork", {"left": "neutron star", "leftNote": "about city-sized", "right": "black hole", "rightNote": "heavier stars", "highlightRightAt": 999},
                    "a fork: collapsed core → neutron star (city-sized) or → black hole", at=0)],
  {"e_stars": STAR_L, "e_fork": P(0.5, 0.5, 0.8, 2)}, {"e_stars": STAR_P, "e_fork": P(0.5, 0.45, 0.96, 2)},
  voice=V("pose the question about the core", "curious", 1, "steady", ["core", "neutron star"]))
S("s30", "blackhole", ["C21_remnant", "C22_horizon"],
  "If the star was heavy enough, nothing can stop the collapse. The core falls in until its gravity is so strong that not even light can escape. That boundary is the event horizon. A black hole is born.",
  "the destination of the whole video", "payoff", "illustration",
  [img("e_bh", "g_blackhole", "illustration: a stellar black hole, dark silhouette ringed by bent light, remnant gas", role="subject"), txt("e_tag", ILLU, "context"),
   txt("e_h", "event horizon", "label", at=26), txt("e_b", "a black hole is born", "subject", at=31)],
  {"e_bh": FULL_L, "e_tag": TAG_L, "e_h": P(0.5, 0.82, 0.28, 3), "e_b": P(0.5, 0.15, 0.38, 3)},
  {"e_bh": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_h": P(0.5, 0.7, 0.56, 3), "e_b": P(0.5, 0.22, 0.76, 3)},
  voice=V("the payoff of the title", "quiet-wonder", 3, "slower", ["nothing", "not even light", "born"], pb=200, pa=600),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.15, "a slow push toward the horizon as the collapse completes")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.12, "slow push toward the horizon")],
  transition={"type": "dissolve", "durationMs": 800})
S("s31", "blackhole", ["C23_eht", "C21_remnant"],
  "This is the first image of a black hole's shadow, from the Event Horizon Telescope in 2019. That one is a giant in the galaxy M87, six and a half billion times the Sun's mass. Black holes left behind by dying stars are far smaller.",
  "real evidence that black holes exist, with an honest scale caveat", "evidence", "archival",
  [img("e_eht", "r_eht", "real Event Horizon Telescope image of the M87 black hole shadow"), txt("e_tag", "Real image · EHT", "context"),
   txt("e_s", "6.5 billion Suns", "label", at=17), txt("e_n", "supermassive", "label", at=28)],
  {"e_eht": FULL_L, "e_tag": TAG_L, "e_s": P(0.17, 0.5, 0.28, 3), "e_n": P(0.83, 0.5, 0.28, 3)},
  {"e_eht": P(0.5, 0.43, 1.0, 1), "e_tag": TAG_P, "e_s": P(0.5, 0.74, 0.86, 3), "e_n": P(0.5, 0.8, 0.7, 3)},
  voice=V("show proof, correct scale", "matter-of-fact", 1, "steady", ["first image", "far smaller"], pron=[("M87", "M eighty-seven")]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.06, "a gentle push on the shadow")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.05, "gentle push on the shadow")])

# ---------- 11 finding ----------
S("s32", "finding", ["C24_binaries"],
  "If light can't escape, how do we know they're there? Because they pull on their neighbors. Nearly every black hole left behind by a dead star that we've found so far is paired with a living star.",
  "the detection question and its answer", "next_question", "illustration",
  [img("e_cyg", "r_cygx1_art", "NASA illustration of Cygnus X-1: a black hole pulling gas from a blue companion star"), txt("e_tag", "NASA illustration", "context"),
   txt("e_l", "paired with a star", "label", at=24)],
  {"e_cyg": FULL_L, "e_tag": TAG_L, "e_l": P(0.5, 0.86, 0.3, 3)}, {"e_cyg": P(0.4, 0.5, 3.0), "e_tag": TAG_P, "e_l": P(0.5, 0.72, 0.6, 3)},
  voice=V("ask, then answer", "curious", 1, "steady", ["how", "pull"], pa=150),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.06, "gentle push on the pair")],
  cam_p=[cam(0.4, 0.5, 1.0, 0.42, 0.5, 1.04, "gentle push on the pair")])
S("s33", "finding", ["C24_binaries", "C25_cygx1"],
  "In Cygnus X-1, a black hole pulls gas off its companion, into a disk hot enough to glow in X-rays. A 2021 study puts that black hole at about twenty-one times the mass of the Sun.",
  "first concrete case", "evidence", "illustration",
  [img("e_cyg", "r_cygx1_art", "same Cygnus X-1 illustration, closer on the disk"), txt("e_tag", "NASA illustration", "context"),
   txt("e_x", "glows in X-rays", "label", at=15), txt("e_m", "≈21 × the Sun", "number", at=25)],
  {"e_cyg": FULL_L, "e_tag": TAG_L, "e_x": P(0.2, 0.84, 0.26, 3), "e_m": P(0.8, 0.84, 0.28, 3)},
  {"e_cyg": P(0.4, 0.5, 3.0), "e_tag": TAG_P, "e_x": P(0.5, 0.66, 0.56, 3), "e_m": P(0.5, 0.74, 0.6, 3)},
  voice=V("give the case", "warm-explanatory", 1, "steady", ["X-rays", "twenty-one"]),
  cam_l=[cam(0.5, 0.5, 1.04, 0.54, 0.5, 1.16, "push toward the glowing disk while it is described")],
  cam_p=[cam(0.42, 0.5, 1.04, 0.46, 0.5, 1.16, "push toward the disk")])
S("s34", "finding", ["C26_gaiabh3"],
  "And in 2024, the Gaia mission noticed an old star wobbling around something unseen, less than two thousand light-years away. It is a black hole about thirty-three times the Sun's mass, the biggest star-made black hole found in our galaxy when it was announced.",
  "the newest record, found by a wobble", "evidence", "illustration",
  [img("e_gaia", "r_gaiabh3_art", "ESO illustration of the Gaia BH3 system: an old star orbiting a dark black hole"), txt("e_tag", "ESO illustration", "context"),
   txt("e_d", "< 2,000 light-years", "label", at=16), txt("e_m", "≈33 × the Sun", "number", at=26)],
  {"e_gaia": FULL_L, "e_tag": TAG_L, "e_d": P(0.2, 0.86, 0.28, 3), "e_m": P(0.8, 0.86, 0.28, 3)},
  {"e_gaia": P(0.5, 0.5, 3.0), "e_tag": TAG_P, "e_d": P(0.5, 0.66, 0.56, 3), "e_m": P(0.5, 0.74, 0.56, 3)},
  voice=V("a fresh discovery", "curious", 2, "steady", ["wobbling", "thirty-three"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.1, "a slow push on the unseen companion")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.08, "slow push on the system")])

# ---------- 12 vanish ----------
S("s35", "vanish", ["C27_n6946"],
  "Some astronomers think a giant star may skip the explosion entirely. In 2009, a red supergiant about twenty-five times the Sun's mass, in another galaxy, flared weakly and then seemed to disappear.",
  "an open question, told honestly", "develop", "archival",
  [img("e_van", "r_n6946", "real Hubble before/after images of the star N6946-BH1"),
   txt("e_a", "before", "label", at=0), txt("e_b", "after", "label", at=25)],
  {"e_van": P(0.5, 0.5, 0.86, 1), "e_a": P(0.27, 0.86, 0.12, 3), "e_b": P(0.73, 0.86, 0.12, 3)},
  {"e_van": P(0.5, 0.45, 1.0, 1), "e_a": P(0.25, 0.64, 0.3, 3), "e_b": P(0.75, 0.64, 0.3, 3)},
  voice=V("introduce a mystery without hype", "curious", 1, "steady", ["skip", "disappear"]),
  cam_l=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.05, "a gentle push while the before/after is compared")],
  cam_p=[cam(0.5, 0.5, 1.0, 0.5, 0.5, 1.04, "gentle push on the comparison")])
S("s36", "vanish", ["C27_n6946"],
  "One explanation is a failed supernova: a star collapsing straight into a black hole, with almost no explosion. But newer telescope data complicate that picture, and astronomers are still debating it.",
  "keep uncertainty visible", "settle", "archival",
  [img("e_van", "r_n6946", "same Hubble before/after images"),
   txt("e_d", "still debated", "label", at=24)],
  {"e_van": P(0.5, 0.5, 0.86, 1), "e_d": P(0.5, 0.86, 0.24, 3)},
  {"e_van": P(0.5, 0.45, 1.0, 1), "e_d": P(0.5, 0.72, 0.5, 3)},
  voice=V("say what is not known", "matter-of-fact", 0, "steady", ["still debating"], pa=500, notes="no drama; the limit of knowledge is the point"),
  cam_l=[cam(0.5, 0.5, 1.05, 0.5, 0.5, 1.1, "continues the slow push")],
  cam_p=[cam(0.5, 0.5, 1.04, 0.5, 0.5, 1.08, "continues the slow push")], transition={"type": "dissolve", "durationMs": 700})

# ---------- 13 close ----------
RECAP = [("g_clump", "cloud"), ("g_protostar", "protostar"), ("g_ignite", "star"), ("g_supergiant", "supergiant"), ("g_supernova", "supernova"), ("g_blackhole", "black hole")]
def recap_entities(first_words):
    ents = [starfield()]
    for i, ((a, lab), at) in enumerate(zip(RECAP, first_words)):
        ents.append(img(f"e_r{i}", a, f"small recap tile: {lab}", role="subject", enter=("rise", 500)))
        ents[-1]["enterAtWord"] = at
        ents.append(txt(f"e_t{i}", lab, "label", at=at))
    return ents
def recap_place(port=False):
    pl = {"e_stars": STAR_P if port else STAR_L}
    for i in range(6):
        col, row = i % 3, i // 3
        x, y = 0.2 + 0.3 * col, 0.25 + 0.38 * row
        pl[f"e_r{i}"] = P(x, y, 0.26, 1); pl[f"e_t{i}"] = P(x, y + 0.19, round(0.017 * len(RECAP[i][1]), 4), 2)
    return pl
S("s37", "close", ["C06_balance"],
  "So that's the whole journey. A cold cloud collapses. A protostar ignites. For millions of years, pressure holds gravity back.",
  "recap part one", "settle", "illustration", recap_entities([5, 9, 12, 99, 99, 99])[:7],
  {k: v for k, v in recap_place().items() if k in ("e_stars", "e_r0", "e_t0", "e_r1", "e_t1", "e_r2", "e_t2")},
  voice=V("gather the threads", "reflective", 1, "steady"),
  hold_l="the recap tiles stay put while the steps are named")
S("s38", "close", ["C16_rebound", "C21_remnant"],
  "Then the fuel runs out, the core collapses, the star explodes, and what's left can fall into a black hole.",
  "recap part two", "settle", "illustration", recap_entities([0, 0, 0, 2, 10, 18]),
  recap_place(),
  voice=V("complete the arc", "reflective", 1, "steady", ["black hole"], pa=300),
  hold_l="all six recap tiles together, the full arc at a glance", transition={"type": "dissolve", "durationMs": 800})
for k in ("e_r0", "e_r1", "e_r2", "e_t0", "e_t1", "e_t2"):
    for e in scenes[-1]["entities"]:
        if e["id"] == k: e["enter"] = {"style": "none", "durationMs": 0}
S("s39", "close", ["C28_enrich", "C01_pillars"],
  "But the story doesn't end in the dark. The gas the star threw away drifts back out, and enriches the next clouds. Clouds like these, where new stars are being born right now.",
  "close the loop honestly: matter returns to new nurseries", "settle", "archival",
  [img("e_pil", "r_pillars", "the real Webb pillars again"), txt("e_tag", REAL_WEBB, "context")],
  {"e_pil": FULL_L, "e_tag": TAG_L},
  voice=V("warm close", "warm-explanatory", 1, "slower", ["next clouds", "right now"], pa=800),
  cam_l=[cam(0.48, 0.44, 1.2, 0.5, 0.5, 1.0, "the pull-back returns to the opening view: the cycle continues")])

# ---------- Shorts ----------
SV = lambda: {"independentOpening": True, "oneQuestion": True, "minimumContext": True, "completeExplanation": True, "cleanPayoff": True, "sourceLinked": True, "deltaDefined": True}
shorts = [
 {"id": "S01", "status": "validated", "title": "Why iron kills the biggest stars", "question": "What actually makes a giant star explode?",
  "minimumContext": ["giant stars stay alive by fusing ever-heavier elements in their core"],
  "payoff": "iron fusion costs energy, the core collapses in under a second and rebounds into a supernova",
  "sceneIds": ["s20", "s21", "s22", "s23"],
  "delta": {"openingLine": "A giant star holds itself up against its own gravity by fusing heavier and heavier elements in its core. Until it reaches iron.",
            "closingLine": "And what's left behind can become a black hole.", "portraitRestage": "onion and core diagrams stacked full-width; labels above and below"},
  "targetDurationS": 50, "validation": SV()},
 {"id": "S02", "status": "validated", "title": "You are made of exploded stars", "question": "Where did the oxygen and calcium in your body come from?",
  "minimumContext": ["a supernova is a giant star exploding"],
  "payoff": "NASA: all the Solar System's oxygen, about half its calcium and ~40% of its iron came from exploding massive stars",
  "sceneIds": ["s27", "s28"],
  "delta": {"openingLine": "The oxygen in your next breath came from exploding stars.",
            "closingLine": "And oxygen alone is about two thirds of your body's weight.", "portraitRestage": "Chandra image top, colour key below; bars full-width"},
  "targetDurationS": 40, "validation": SV()},
 {"id": "S03", "status": "validated", "title": "The moment a star switches on", "question": "What turns a cloud of gas into a shining star?",
  "minimumContext": ["stars form inside cold clouds of gas and dust"],
  "payoff": "at about fifteen million degrees hydrogen fuses into helium: a star is born",
  "sceneIds": ["s06", "s07", "s08", "s10", "s11"],
  "delta": {"openingLine": "Every star begins inside a cold, dark cloud of gas and dust, where the gas gathers into dense clumps.", "portraitRestage": "illustrations recomposed tall; temperature readout centred"},
  "targetDurationS": 50, "validation": SV()},
 {"id": "S04", "status": "validated", "title": "How do you find something invisible?", "question": "If black holes give off no light, how do we find them?",
  "minimumContext": ["no light escapes a black hole"],
  "payoff": "by their pull on companion stars: Cygnus X-1 (~21 Suns) glows in X-rays; Gaia BH3 (~33 Suns) was found by a wobble",
  "sceneIds": ["s32", "s33", "s34"],
  "delta": {"openingLine": "Nothing escapes a black hole, not even light.", "portraitRestage": "illustrations recomposed tall; numbers stacked"},
  "targetDurationS": 55, "validation": SV()},
 {"id": "S05", "status": "validated", "title": "The giant star that vanished", "question": "Can a giant star turn into a black hole without exploding?",
  "minimumContext": ["most giant stars die in a supernova explosion"],
  "payoff": "N6946-BH1 flared weakly and seemed to vanish; a failed supernova is one explanation, still debated",
  "sceneIds": ["s35", "s36"],
  "delta": {"openingLine": "Most giant stars die in a huge explosion. But maybe not all of them.",
            "closingLine": "If the failed-supernova idea is confirmed, astronomers say it would be the first time anyone has seen a black hole being born.", "portraitRestage": "before/after stacked tall"},
  "targetDurationS": 40, "validation": SV()},
 {"id": "S06", "status": "rejected", "title": "Why giant stars die young", "question": "Why do heavier stars live shorter lives?",
  "minimumContext": ["stars burn hydrogen"], "payoff": "heavier stars burn faster", "sceneIds": ["s14", "s15"],
  "delta": {"openingLine": "The biggest stars live the shortest lives."}, "targetDurationS": 30,
  "validation": {**SV(), "completeExplanation": False, "cleanPayoff": False},
  "rejectedReason": "two diagram scenes give a fact but no complete visual explanation or payoff a stranger would feel; five stronger Shorts exist"},
]
by_id = {s["id"]: s for s in scenes}
for sh in shorts:
    if sh["status"] == "validated":
        for sid in sh["sceneIds"]: by_id[sid]["shortIds"].append(sh["id"])
# every scene used by a Short needs a portrait layout: the rest keep landscape only
for sc in scenes:
    if sc["shortIds"] and "portrait" not in sc["layouts"]: raise SystemExit(f"{sc['id']} is in a Short but has no portrait layout")
    pt = sc["layouts"].get("portrait")
    if pt and any(abs(v["w"] - 3.0) < 1e-6 for v in pt["placements"].values()):
        # a 16:9 plate at w=3.0 is 1822 px tall in a 1920 px frame: keep the camera at >= 1.06x so it always covers the frame
        for c in pt["camera"]:
            c["from"]["scale"] = round(c["from"]["scale"] + 0.06, 3); c["to"]["scale"] = round(c["to"]["scale"] + 0.06, 3)
    if pt:
        # keep portrait labels above the caption band (captions sit around 0.78-0.86 of the height)
        texts = {e["id"] for e in sc["entities"] if e.get("text")}
        for k, v in pt["placements"].items():
            if k in texts and 0.6 < v["y"] <= 0.9: v["y"] = round(v["y"] - 0.08, 3)
    lt = sc["layouts"]["landscape"]
    ltexts = {e["id"] for e in sc["entities"] if e.get("text")}
    for k, v in lt["placements"].items():
        if k in ltexts and v["y"] > 0.78: v["y"] = 0.75   # landscape captions own the band below ~0.8
    for e in sc["entities"]:
        if e["id"] in ("e_tag", "e_ill") and e.get("text"):
            label = e.pop("text"); n = len(label)
            e["role"] = "context"; e["need"] = "provenance tag on a translucent pill"
            if not NO_ASSETS: e["visual"] = {"component": "tag", "props": {"text": label}}
            wl = round((36 * n + 80) * 0.000358, 4)
            lay = lt["placements"][e["id"]]
            if e["id"] == "e_tag": lay.update({"w": wl, "x": round(0.94 - wl / 2, 4), "y": 0.085})
            else: lay["w"] = wl
            lay["depth"] = 1.0
            if pt and e["id"] in pt["placements"]: pt["placements"][e["id"]].update({"w": round(min(0.8, (36 * n + 80) * 0.000637), 4), "depth": 1.0})
    for lay in sc["layouts"].values():
        for k, v in lay["placements"].items():
            if k in ltexts: v["depth"] = 1.0   # labels follow the camera less (parallax), so pushes never carry them off-frame
    if not NO_ASSETS:
        sc["assetIds"] = sorted({e["assetId"] for e in sc["entities"] if e.get("assetId")})

# stage 03: timing comes from the FINAL audio's alignment (contiguous scene windows; boundary = midpoint of the silence between scenes)
_al = os.path.join(HERE, "audio", "alignment.json")
if os.path.exists(_al) and not NO_ASSETS:
    _b = {x["sceneId"]: x for x in json.load(open(_al)).get("sceneBounds", [])}
    if all(sc["id"] in _b for sc in scenes):
        for sc in scenes:
            x = _b[sc["id"]]
            sc["timing"] = {"startS": x["startS"], "endS": x["endS"], "firstWord": x["firstWord"], "lastWord": x["lastWord"]}

    # the iron shell appears on the word "iron" (scene-relative seconds from the alignment)
    for sc in scenes:
        if sc["id"] == "s20" and not NO_ASSETS:
            words = json.load(open(_al))["words"]
            ws = [w for w in words if w.get("scene") == "s20"]
            iw = next(w for w in ws if w["w"].lower().startswith("iron"))
            for e in sc["entities"]:
                if e["id"] == "e_onion": e["visual"]["props"]["ironAtS"] = round(iw["s"] - ws[0]["s"], 2)
doc = {"schemaVersion": 1, "fps": 30, "opening": {"fadeInMs": 400, "leadSilenceMs": 500}, "ending": {"fadeOutMs": 1200, "holdBlackMs": 600, "tailSilenceMs": 1200}, "scenes": scenes}
json.dump(doc, open(os.path.join(HERE, "scenes.json"), "w"), indent=1, ensure_ascii=False)
json.dump({"shorts": shorts}, open(os.path.join(HERE, "shorts.json"), "w"), indent=1, ensure_ascii=False)
secs, out = [], []
for sc in scenes:
    if not secs or secs[-1][0] != sc["section"]: secs.append((sc["section"], []))
    secs[-1][1].append(sc["narration"])
open(os.path.join(HERE, "spoken_script.txt"), "w").write("\n\n".join(" ".join(t) for _, t in secs) + "\n")
words = sum(len(s["narration"].split()) for s in scenes)
print(f"{len(scenes)} scenes, {words} words, ~{words/155*60:.0f}s at 155 wpm; shorts validated: {sum(s['status']=='validated' for s in shorts)}")
