# Style presets and the style bible (read in stage 02)

A preset is a starting set of decisions for a kind of topic, not a template. Choose one or two, change at least two parameters to fit this topic, and write the result into `style-bible.md` and `style-tokens.json`. No preset is the default; ink-and-paper is one of ten.

## 1. Procedure
1. Topic read: subject · evidence type (observation, documents, models, human accounts, data) · emotional register the facts earn · audience.
2. Pick one or two presets below (a hybrid takes the ground and light from one, the diagram language from the other).
3. Set tokens, compute contrast (`python tools/contrast.py --tokens style-tokens.json`), render one style tile by code, look at it, fix it.
4. Anti-clone check against the last 3 files in `library/style-bibles/`: differ in at least 2 of the four dimensions below, unless `channel.md` fixes brand constants. Record the comparison.

Dimensions (use these words in `dimensions` so the comparison is objective):
- palette family: warm-paper · earth-natural · cool-night · ink-dark · mono-editorial · pastel-soft · saturated-pop · duotone
- texture: paper-fibre · film-grain · clean-vector · canvas-gouache · blueprint-grid · halftone · none
- motion language: still-with-cuts · slow-drift · parallax-layers · precise-mechanical · handheld-organic · kinetic-type · map-travel
- composition: centred-icon · map-first · timeline-strip · split-compare · full-bleed-plate · specimen-on-ground · layered-diorama

## 2. Presets
**1 Ink & Paper.** Fits: mechanisms and ideas explained to a general audience. Warm off-white ground, near-black ink, one accent reserved for the thing being explained. Paper fibre, faint grain. Humanist type; captions in ink on paper strips. Slow parallax on layered drawings; stillness while labels arrive. Centred-icon or split-compare. Mix: mostly code (SVG line art) plus 1–2 generated ink-wash hero plates. Avoid: one accent colour on every topic; magnifier circles and drifting glow as decoration.

**2 Deep Field.** Fits: space, physics, deep time, scale. Near-black (not pure black), one warm light accent and one cool neutral for geometry, fine star grain, no lens flare. Light type, generous tracking on labels. Slow dolly through depth layers; long holds on scale ladders. Full-bleed plates with diagram overlays. Mix: code geometry and scale ladders; at most two generated plates labelled as illustration; real observational images only from sources with a license, described as what they are. Avoid: fake photographs of what cannot be observed; wall-to-wall glowing particles; certainty beyond the evidence.

**3 Archive & Annotation.** Fits: history, civilisations, case studies with documents. Aged neutrals (parchment, umber, faded red, slate), archival grain, hairline map linework. Classical serif or typewriter labels; captions as document slips. Map travel, restrained pans, reveal by uncovering; plain cuts for chronology. Map-first, timeline strips, document-and-annotation. Mix: retrieved public-domain material first (license evidence), code maps from open geodata, reconstructions labelled "reconstruction". Avoid: modern-looking generated images presented as evidence; space zooms; forced morphs.

**4 Blueprint & Mechanism.** Fits: engineering, technology, anything built or working inside. Graphite or deep-ink ground with pale linework and one signal colour (blue is traditional, not required). Consistent line weights, exploded views, leader-line callouts, monospaced labels. Precise-mechanical motion: assemble, disassemble, travel along paths with easing. Specimen or diagram centred. Mix: all code; generated images only for real-world context. Avoid: decoration that competes with the mechanism.

**5 Warm Gouache.** Fits: psychology, memory, human stories, everyday life. Daylight palette of warm neutrals with two muted accents, gouache or canvas texture, soft edges, no cinematic darkness. Rounded humanist type. Gentle push-ins, long stills, soft dissolves, plain cuts between scenes. Layered-diorama of everyday scenes; split-compare "what happened / what is remembered". Mix: 3–5 generated hero plates kept consistent with a reference image, plus code shapes; simple, non-specific characters. Avoid: glowing-brain imagery, horror lighting, overconfident explanations.

**6 Editorial Data.** Fits: economics, statistics, comparisons. Neutral light or dark ground, strict grid, one accent for the variable the story is about and one for the comparison, no texture. Clean sans, tabular numerals, direct labels. Charts draw as the narration states the values; stillness between. Split-compare, small multiples. Mix: all code. Avoid: misleading dual axes, silent axis truncation, decorative 3D.

**7 Specimen Studio.** Fits: biology, nature, objects, materials. Neutral seamless ground (warm grey or deep green-black), soft studio light, scientific labels with leader lines and scale bars. Quiet serif captions. Slow turntable-like parallax, macro push-ins. Specimen-on-ground. Mix: licensed photographs (open museum and collection archives) or generated specimens labelled as illustration; code labels. Avoid: letting a generated creature pass as a photograph.

**8 Layered Paper Cut-out.** Fits: playful topics, complex-made-simple. Controlled saturated palette, paper edges with soft shadows, layered depth, rounded display type. Parallax is natural and cheap: layers drift, shapes pop in on their words. Layered-diorama. Mix: nearly all code-made shapes. Avoid: clutter; every layer moving at once.

**9 Cartographic.** Fits: geography, migration, empires, logistics, climate across regions. Muted land and sea with one route colour, hairline graticule, clear label hierarchy. Routes draw on (path evolve), eased pans between regions, stillness on dense labels. Map-first. Mix: code maps from open data (license logged), retrieved imagery for places. Avoid: modern borders implying claims about past periods; unlabelled projections where area comparison matters.

**10 Quiet Documentary.** Fits: care and high sensitivity (health, tragedy, politics, religion, personal finance). Restrained neutrals, natural light logic, mostly stills with long holds and plain cuts, sources and captions prominent, no stylised drama. Neutral type with high contrast. No signature transitions; music none or barely present. Mix: licensed archival material or clearly stylised illustration; code for data. Avoid: sensational crops, dramatic zooms on suffering, decorative effects.

## 3. The style bible (what `style-bible.md` must contain)
Topic read · presets used and what you changed · palette tokens with computed contrast · lighting logic (direction, hardness, colour temperature) · texture and grain · typography (fonts with a license, for example SIL OFL families; the font files go in `library/fonts/` and are loaded by name from the style tokens: the renderer never falls back to a system font silently) and the minimum text height · caption style · motion language (easing token mapping, camera vocabulary, what never moves) · composition rules for both aspect ratios · the unifying grade · a "must not look like" list · rationale in 6 lines or fewer.

`style-tokens.json`:
```json
{"preset":["archive-annotation","cartographic"],
 "dimensions":{"paletteFamily":"earth-natural","texture":"film-grain","motion":"map-travel","composition":"map-first"},
 "palette":{"bg":"#…","surface":"#…","ink":"#…","muted":"#…","accent":"#…","accent2":"#…"},
 "textPairs":[["ink","bg"],["muted","bg"],["ink","surface"]],
 "graphicPairs":[["accent","bg"],["accent2","bg"]],
 "type":{"display":"…","body":"…","label":"…","minTextPx1080":48},
 "easing":{"standard":[0.4,0,0.2,1],"emphasized":[0.65,0,0.35,1],"soft":[0.37,0,0.63,1]},
 "grade":{"matrix":[1,0,0, 0,1,0, 0,0,1],"grain":0.04,"vignette":0.2},
 "captions":{"font":"…","size1080":56,"weight":600,"background":"surface at 0.78 opacity"},
 "looks":{"base":{},"dusk":{"grade":{"matrix":[…]}}}}
```

## 4. Mixed media under a small ceiling
With 15–20 credits most videos mix code graphics, retrieved plates and a few generated hero images. Spend credits where they change what the viewer feels: the opening frame, the payoff or reveal plates, the level-3 moments. Everything else is code or retrieved. They read as one world when they share one **grade** applied in code over everything: a common colour mapping, grain and vignette, one light direction, one line-weight family, one edge treatment, one shadow logic. Build a **lineup sheet** (one hero plate, one code diagram, one retrieved image, one label, side by side under the grade) and fix it until they look like siblings.

## 5. Colour script (optional)
A deliberate palette or grade shift by section (calm, tension, resolution) carries emotion without effects. Define named `looks` in the tokens and set `scene.look`. Keep the hue family, use at most three looks, shift on transitions rather than mid-scene, and re-check contrast for each look.

## 6. Prompts for generated images
what it is · composition (central subject, room to crop for 16:9 and 9:16, subject inside the central region) · the bible's phrases for light, palette words, texture and medium · "no text, no labels, no numbers, no watermark". Describe a look in words; never name living artists, studios, characters or brands (H2). Labels and numbers are always live text in code.
