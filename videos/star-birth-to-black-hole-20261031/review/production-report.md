# Production report - star-birth-to-black-hole-20261031

Idea: How a star is born from the very first moment until it dies and becomes a black hole  ·  purpose: **production**  ·  made 2026-10-31T16:12:02

## Gate verdicts

| target | file | media QA | motion QA | length | size |
|---|---|---|---|---|---|
| long | out/full-video.mp4 | PASSED | PASSED | 476.267 s | 1920x1080 |

A verdict is the gate's own result on the delivered file. WARN items are heuristics and are listed under "A person still has to look at". PASSED never means the video is good, only that none of these checks found a defect.

## Transitions

- long s02>s03: **dissolve**
- long s06>s07: **nested_scale**
- long s10>s11: **dissolve**
- long s19>s20: **dissolve**
- long s22>s23: **occlusion_reveal**
- long s25>s26: **dissolve**
- long s30>s31: **dissolve**
- long s36>s37: **dissolve**
- long s38>s39: **dissolve**

## Render

- long: 14288 frames at 30 fps, 79.1 ms/frame with 4 worker(s) = 1130.5 s of capture on this machine; a 60 fps render would take about 37.7 min

## Voice and alignment

- voice: file / externally supplied - as supplied
- alignment: whisper, coverage 1.0, median confidence 0.994; whisper (small.en, faster-whisper word timestamps) mapped onto the script: 1046/1058 script words matched a recognised word (98.9%); the rest are interpolated between matched neighbours (confidence 0.3); 26 words have confidence < 0.35: listen to them before trusting their timing

## Spend

| service | approved | ceiling | spent | in flight |
|---|---|---|---|---|
| elevenlabs | no | 0.0 chars | 0.0 | 0.0 |
| higgsfield | yes | 38.0 credits | 34.35 | 0.0 |
| music | no | 0.0 usd | 0.0 | 0.0 |
| stock | no | 0.0 usd | 0.0 | 0.0 |

Creative preview gate: approved 2026-10-31T13:36:04 (creator chose 'cheaper approval, ceiling 38' (Knox via Higgsfield + nano_banana_2 2k illustrations))

## A person still has to look at

- long: motion.s10>s11.audio (heuristic warning) - abrupt audio at 101.73s click 10.5
- long: motion.s22>s23.smooth (heuristic warning) - a frame step is 2.8 levels above its neighbours' typical 2.6 (a jerk; smaller than a pop)
- evidence: C01_pillars.evidence[0]: does this passage state the claim? ESA/Webb states the pillars are a site of ongoing star formation imaged by Webb. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C01_pillars.evidence[1]: does this passage state the claim? NASA confirms the pillars are cool gas and dust (the 'cold gas and dust' wording). -> read the quote next to the claim text and confirm it says the same thing
- evidence: C02_cloud.evidence[0]: does this passage state the claim? Gives the mass range (upper end 10 million solar masses) and size. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C02_cloud.evidence[1]: does this passage state the claim? Supports cold-gas clumping, growth by collision/accretion and gravitational collapse. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C02_cloud.evidence[2]: does this passage state the claim? Independent NASA HEASARC page: stars begin from collapse in molecular clouds. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C03_protostar.evidence[0]: does this passage state the claim? Collapse heats material; a protostar ('baby star') forms. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C03_protostar.evidence[1]: does this passage state the claim? Supports 'its glow comes from the heat of its own collapse'. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C03_protostar.evidence[2]: does this passage state the claim? Supports 'it isn't burning anything yet'. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C04_jets.evidence[0]: does this passage state the claim? Describes the red jets and when they occur. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C04_jets.evidence[1]: does this passage state the claim? Independent page: young stars shoot out jets. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C05_ignition.evidence[0]: does this passage state the claim? Gives the ~15 million K threshold (narration says 'about fifteen million degrees'; kelvin and °C differ negligibly at this scale). -> read the quote next to the claim text and confirm it says the same thing
- evidence: C05_ignition.evidence[1]: does this passage state the claim? Supports squeezing hydrogen nuclei into helium and energy release. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C06_balance.evidence[0]: does this passage state the claim? States the balance of gravity and pressure. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C06_balance.evidence[1]: does this passage state the claim? Fusion heat holds the star up. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C07_mainseq.evidence[0]: does this passage state the claim? Main sequence is the longest phase. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C07_mainseq.evidence[1]: does this passage state the claim? Sun is roughly halfway. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C07_mainseq.evidence[2]: does this passage state the claim? Independent confirmation. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C08_mass_rate.evidence[0]: does this passage state the claim? Heavier stars burn faster to hold up their weight. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C08_mass_rate.evidence[1]: does this passage state the claim? Few-million-year lifetimes. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C08_mass_rate.evidence[2]: does this passage state the claim? Sun's ~10 billion years. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C08_mass_rate.evidence[3]: does this passage state the claim? Supports 'depends, above all, on mass'. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C09_whitedwarf.evidence[0]: does this passage state the claim? White dwarf: Earth-sized cooling cinder. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C09_whitedwarf.evidence[1]: does this passage state the claim? The Sun follows this path. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C09_whitedwarf.evidence[2]: does this passage state the claim? Independent: white-dwarf endpoint below ~8 solar masses. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C10_sn_threshold.evidence[0]: does this passage state the claim? 8 solar mass threshold. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C10_sn_threshold.evidence[1]: does this passage state the claim? Independent NASA page, same threshold. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C11_bh_threshold.evidence[0]: does this passage state the claim? Around 20 solar masses or more. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C11_bh_threshold.evidence[1]: does this passage state the claim? Same threshold, older NASA page. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C12_supergiant.evidence[0]: does this passage state the claim? High-mass stars become red supergiants. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C12_supergiant.evidence[1]: does this passage state the claim? Core squeezed and heated, outer layers expand. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C12_supergiant.evidence[2]: does this passage state the claim? Trigger: core hydrogen runs out. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C13_chain.evidence[0]: does this passage state the claim? The chain up to silicon to iron. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C13_chain.evidence[1]: does this passage state the claim? Each fuel buys less time. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C13_chain.evidence[2]: does this passage state the claim? Final stage lasts days. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C13_chain.evidence[3]: does this passage state the claim? Helium to carbon. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C13_chain.evidence[4]: does this passage state the claim? Carbon to neon. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C14_iron.evidence[0]: does this passage state the claim? Iron costs energy; the star loses to gravity. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C14_iron.evidence[1]: does this passage state the claim? Independent Chandra page. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C14_iron.evidence[2]: does this passage state the claim? Third NASA page. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C15_collapse.evidence[0]: does this passage state the claim? Under one second; over 100 billion degrees. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C15_collapse.evidence[1]: does this passage state the claim? Same statement on sibling page (same institution). -> read the quote next to the claim text and confirm it says the same thing
- evidence: C16_rebound.evidence[0]: does this passage state the claim? Rebound, shock wave, supernova. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C16_rebound.evidence[1]: does this passage state the claim? Remnant types. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C17_outshine.evidence[0]: does this passage state the claim? Direct statement. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C18_crab.evidence[0]: does this passage state the claim? All parts of the claim. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C19_casa.evidence[0]: does this passage state the claim? Elements mapped in the image. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C20_elements.evidence[0]: does this passage state the claim? Element fractions as stated by NASA/Chandra. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C20_elements.evidence[1]: does this passage state the claim? Calcium in bones. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C20_elements.evidence[2]: does this passage state the claim? Supports the Short's line that oxygen is about two thirds of body weight. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C21_remnant.evidence[0]: does this passage state the claim? City-sized neutron star. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C21_remnant.evidence[1]: does this passage state the claim? For heavy enough stars nothing halts collapse. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C22_horizon.evidence[0]: does this passage state the claim? Direct statement. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C22_horizon.evidence[1]: does this passage state the claim? Independent ESO statement. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C23_eht.evidence[0]: does this passage state the claim? First image of a black hole's shadow. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C23_eht.evidence[1]: does this passage state the claim? Mass and distance. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C23_eht.evidence[3]: does this passage state the claim? Star-made black holes: a few to hundreds of solar masses, far below 6.5 billion. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C24_binaries.evidence[0]: does this passage state the claim? States the claim directly. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C24_binaries.evidence[1]: does this passage state the claim? X-ray binaries mechanism. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C25_cygx1.evidence[0]: does this passage state the claim? Peer-reviewed mass estimate. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C25_cygx1.evidence[1]: does this passage state the claim? Cyg X-1 is an X-ray binary (supports the gas-pulling scene). -> read the quote next to the claim text and confirm it says the same thing
- evidence: C26_gaiabh3.evidence[0]: does this passage state the claim? Mass, distance, record. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C26_gaiabh3.evidence[1]: does this passage state the claim? An old star. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C26_gaiabh3.evidence[2]: does this passage state the claim? Found by the star's wobble. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C27_n6946.evidence[0]: does this passage state the claim? ~25 solar-mass red supergiant, weak 2009 outburst, then optical disappearance. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C27_n6946.evidence[1]: does this passage state the claim? Newer JWST data complicate the picture. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C27_n6946.evidence[2]: does this passage state the claim? Status: unconfirmed candidate. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C28_enrich.evidence[0]: does this passage state the claim? States the claim directly. -> read the quote next to the claim text and confirm it says the same thing
- evidence: C28_enrich.evidence[1]: does this passage state the claim? Independent Chandra page. -> read the quote next to the claim text and confirm it says the same thing

## Reproduce

Engine 3.0.0-dom (browser, Chromium 153.0.8010.12); `python tools/pipeline.py run --project /home/user/Ai-youtube-video-1/videos/star-birth-to-black-hole-20261031` reproduces these files byte for byte on the same versions and worker count (the render is reproducible).
