import json, hashlib, sys
P="videos/star-birth-to-black-hole-20261031"
SRC={
 "nasa_stars":("Stars - NASA Science","https://science.nasa.gov/universe/stars/","institution"),
 "imagine_stars":("Stars - Imagine the Universe (NASA GSFC HEASARC)","https://imagine.gsfc.nasa.gov/science/objects/stars1.html","institution"),
 "imagine_sn":("Supernovae - Imagine the Universe (NASA GSFC HEASARC)","https://imagine.gsfc.nasa.gov/science/objects/supernovae1.html","institution"),
 "nasa_bh":("Black Holes - NASA Science","https://science.nasa.gov/universe/black-holes/","institution"),
 "nasa_bh_types":("Black Hole Types - NASA Science","https://science.nasa.gov/universe/black-holes/types/","institution"),
 "webb_pillars":("Webb: Pillars of Creation (weic2216) - ESA/Webb","https://esawebb.org/news/weic2216/","institution"),
 "nasa_pillars":("NASA's Webb Takes Star-Filled Portrait of Pillars of Creation - NASA","https://science.nasa.gov/missions/webb/nasas-webb-takes-star-filled-portrait-of-pillars-of-creation/","institution"),
 "webb_rhooph":("Webb celebrates first year of science with close-up on birth of Sun-like stars (weic2316) - ESA/Webb","https://esawebb.org/news/weic2316/","institution"),
 "nasa_crab":("Messier 1 (The Crab Nebula) - NASA Science","https://science.nasa.gov/mission/hubble/science/explore-the-night-sky/hubble-messier-catalog/messier-1/","institution"),
 "chandra_casa_life":("Cassiopeia A: The Elements of Life - NASA Chandra","https://chandra.harvard.edu/photo/2017/casa_life/","institution"),
 "esahubble_sn":("Distant Supernova 3 - After Outburst (opo0412i) - ESA/Hubble","https://esahubble.org/images/opo0412i","institution"),
 "eso_eht":("Astronomers Capture First Image of a Black Hole (eso1907) - ESO","https://www.eso.org/public/news/eso1907/","institution"),
 "arxiv_cygx1":("Miller-Jones et al. 2021, Cygnus X-1 contains a 21-solar mass black hole (Science; arXiv:2102.09091)","https://arxiv.org/abs/2102.09091","peer_reviewed"),
 "esa_gaiabh3":("Sleeping giant surprises Gaia scientists - ESA (16/04/2024)","https://www.esa.int/Science_Exploration/Space_Science/Gaia/Sleeping_giant_surprises_Gaia_scientists","institution"),
 "gsfc_vanished":("Star Gives Birth to Possible Black Hole in Hubble and Spitzer Images - NASA SVS","https://svs.gsfc.nasa.gov/12621/","institution"),
 "arxiv_n6946":("Adams et al. 2017, The search for failed supernovae with the LBT: confirmation of a disappearing star (MNRAS; arXiv:1609.01283)","https://arxiv.org/abs/1609.01283","peer_reviewed"),
 "arxiv_n6946_jwst":("Beasor et al. 2024, JWST reveals a luminous infrared source at the position of the failed supernova candidate N6946-BH1 (arXiv:2309.16121)","https://arxiv.org/abs/2309.16121","peer_reviewed"),
}
SRC["chandra_sn_guide"]=("Supernovas & Supernova Remnants - NASA Chandra field guide","https://chandra.harvard.edu/xray_sources/supernovas.html","institution")
def sha(f): return hashlib.sha256(open(f,"rb").read()).hexdigest()
def ev(src, i, quote, supports, interp, unc="none"):
    f=f"research/sources/{src}.txt"; text=open(f"{P}/{f}").read()
    if quote not in text: sys.exit(f"QUOTE NOT FOUND in {src}: {quote[:80]}")
    return {"sourceIndex":i,"locator":{"kind":"quote","value":quote[:60]},"quote":quote,"snapshot":f,"snapshotSha256":sha(f"{P}/{f}"),"snapshotKind":"extracted","supports":supports,"interpretation":interp,"uncertainty":unc}
def claim(cid, text, spoken, srcs, evs, status="verified", note=None):
    c={"id":cid,"text":text,"spokenWording":spoken,"sources":[{"title":SRC[s][0],"url":SRC[s][1],"type":SRC[s][2],"accessed":"2026-10-31"} for s in srcs],"evidence":evs,"status":status}
    if note: c["note"]=note
    return c
C=[]
C.append(claim("C01_pillars","Webb's image of the Pillars of Creation shows a region where new stars are forming within dense clouds of gas and dust.","a place where stars are being born right now: the Pillars of Creation, seen by the James Webb Space Telescope",["webb_pillars","nasa_pillars"],[
 ev("webb_pillars",0,"the iconic Pillars of Creation – where new stars are forming within dense clouds of gas and dust","direct","ESA/Webb states the pillars are a site of ongoing star formation imaged by Webb."),
 ev("nasa_pillars",1,"These columns are made up of cool interstellar gas and dust","direct","NASA confirms the pillars are cool gas and dust (the 'cold gas and dust' wording).")]))
C.append(claim("C02_cloud","Stars form in cold molecular clouds of 1,000 to 10 million solar masses spanning up to hundreds of light-years; cold gas clumps, clumps grow by collision or accretion, and gravity makes some collapse.","These clouds can hold up to ten million times the mass of the Sun, and stretch hundreds of light-years across. They are cold, and cold gas clumps together.",["nasa_stars","imagine_stars"],[
 ev("nasa_stars",0,"Molecular clouds range from 1,000 to 10 million times the mass of the Sun and can span as much as hundreds of light-years.","direct","Gives the mass range (upper end 10 million solar masses) and size."),
 ev("nasa_stars",0,"Molecular clouds are cold which causes gas to clump, creating high-density pockets. Some of these clumps can collide with each other or collect more matter, strengthening their gravitational force as their mass grows. Eventually, gravity causes some of these clumps to collapse.","direct","Supports cold-gas clumping, growth by collision/accretion and gravitational collapse."),
 ev("imagine_stars",1,"All stars begin their lives from the collapse of material in a giant molecular cloud.","direct","Independent NASA HEASARC page: stars begin from collapse in molecular clouds.")]))
C.append(claim("C03_protostar","As a clump collapses the material heats up and a protostar (a baby star) forms; before fusion its energy comes from the heat of the collapse.","a hot, dense knot forms: a protostar. A baby star. It isn't burning anything yet. Its glow comes from the heat of its own collapse.",["nasa_stars","imagine_stars"],[
 ev("nasa_stars",0,"friction causes the material to heat up, which eventually leads to the development of a protostar – a baby star.","direct","Collapse heats material; a protostar ('baby star') forms."),
 ev("nasa_stars",0,"At first, most of the protostar’s energy comes from heat released by its initial collapse.","direct","Supports 'its glow comes from the heat of its own collapse'."),
 ev("imagine_stars",1,"Before a star reaches the main sequence, the star is contracting and its core is not yet hot or dense enough to begin nuclear reactions.","direct","Supports 'it isn't burning anything yet'.")]))
C.append(claim("C04_jets","Young stars shoot out jets; Webb's Rho Ophiuchi image shows huge red bipolar jets that occur when a star first bursts through its natal dust envelope; the region is 390 light-years away (nearest star-forming region).","In this Webb image of a nearby nursery, the red streaks are jets, launched as young stars first burst out of their dusty cocoons.",["webb_rhooph","webb_pillars"],[
 ev("webb_rhooph",0,"Huge red bipolar jets of molecular hydrogen dominate the image, appearing horizontally across the upper third and vertically on the right. These occur when a star first bursts through its natal envelope of cosmic dust, shooting out a pair of opposing jets into space.","direct","Describes the red jets and when they occur."),
 ev("webb_pillars",1,"Young stars periodically shoot out jets that collide with clouds of material","direct","Independent page: young stars shoot out jets.")]))
C.append(claim("C05_ignition","When the protostar's core reaches about 15 million kelvin, hydrogen fuses into helium; fusion releases energy and the star enters the main sequence.","At about fifteen million degrees ... Hydrogen nuclei are squeezed together so hard that they fuse into helium. That's nuclear fusion, and it releases energy.",["imagine_stars","nasa_stars"],[
 ev("imagine_stars",0,"It needs to be 15 million Kelvin in the core for fusion to begin.","direct","Gives the ~15 million K threshold (narration says 'about fifteen million degrees'; kelvin and °C differ negligibly at this scale)."),
 ev("nasa_stars",1,"immense pressures and temperatures in the star’s core squeeze the nuclei of hydrogen atoms together to form helium, a process called nuclear fusion. Nuclear fusion releases energy","direct","Supports squeezing hydrogen nuclei into helium and energy release.")]))
C.append(claim("C06_balance","A star's life is a struggle between gravity pulling inward and pressure from its hot core pushing outward (hydrostatic equilibrium); fusion's energy keeps the star from collapsing.","Gravity pulls every layer of the star inward. The heat from fusion pushes outward. As long as the two stay balanced, the star is stable.",["imagine_stars","nasa_stars"],[
 ev("imagine_stars",0,"A star is okay as long as the star has this equilibrium between gravity pulling the star inwards and pressure pushing the star outwards.","direct","States the balance of gravity and pressure."),
 ev("nasa_stars",1,"Nuclear fusion releases energy, which heats the star and prevents it from further collapsing under the force of gravity.","direct","Fusion heat holds the star up.")]))
C.append(claim("C07_mainseq","Stable hydrogen fusion is the main sequence, the longest phase of a star's life; the Sun is roughly midway through it.","Astronomers call this the main sequence. It's the longest phase of a star's life, and our Sun is roughly halfway through its own.",["nasa_stars","imagine_stars"],[
 ev("nasa_stars",0,"This is the longest phase of a star’s life.","direct","Main sequence is the longest phase."),
 ev("nasa_stars",0,"Our Sun is roughly midway through its main sequence stage.","direct","Sun is roughly halfway."),
 ev("imagine_stars",1,"This is also the longest phase of a star's life.","direct","Independent confirmation.")]))
C.append(claim("C08_mass_rate","More massive stars must burn fuel faster to keep from collapsing under their own weight; the Sun spends about 10 billion years on the main sequence while some massive stars live only a few million years.","A heavier star has to burn its fuel much faster, just to hold up its own weight. The Sun will spend about ten billion years on the main sequence. Some massive stars live for only a few million.",["nasa_stars","imagine_stars"],[
 ev("nasa_stars",0,"More massive stars must burn fuel at a higher rate to generate the energy that keeps them from collapsing under their own weight.","direct","Heavier stars burn faster to hold up their weight."),
 ev("nasa_stars",0,"some massive stars will live for only a few million years","direct","Few-million-year lifetimes."),
 ev("imagine_stars",1,"Our sun will spend about 10 billion years on the main sequence.","direct","Sun's ~10 billion years."),
 ev("imagine_stars",1,"The fate and life of a star depends primarily on it's mass.","direct","Supports 'depends, above all, on mass'.")]))
C.append(claim("C09_whitedwarf","Lower-mass stars like the Sun shed their outer layers and end as a white dwarf, a roughly Earth-sized stellar cinder that cools over billions of years.","Stars like the Sun finish quietly, as a white dwarf: a cooling cinder about the size of Earth.",["nasa_stars","imagine_sn"],[
 ev("nasa_stars",0,"All that’s left of the star is its core, now called a white dwarf, a roughly Earth-sized stellar cinder that gradually cools over billions of years.","direct","White dwarf: Earth-sized cooling cinder."),
 ev("nasa_stars",0,"(This will be the fate of our Sun, in several billion years.)","direct","The Sun follows this path."),
 ev("imagine_sn",1,"A white dwarf is the endpoint for stars of up to about 8 times that of the Sun.","direct","Independent: white-dwarf endpoint below ~8 solar masses.")]))
C.append(claim("C10_sn_threshold","Stars of about 8 or more solar masses end their lives as supernovae.","Stars born with more than about eight times the Sun's mass end their lives by exploding.",["imagine_sn","nasa_bh_types"],[
 ev("imagine_sn",0,"Stars which are 8 times or more massive than our Sun end their lives in a most spectacular way; they go supernova.","direct","8 solar mass threshold."),
 ev("nasa_bh_types",1,"When a star with more than eight times the Sun’s mass runs out of fuel, its core collapses, rebounds, and explodes as a supernova.","direct","Independent NASA page, same threshold.")],
 note="Narration no longer says 'only': white dwarfs in binaries can also explode (Type Ia), which the video does not discuss."))
C.append(claim("C11_bh_threshold","Roughly 20 or more solar masses is usually given as the starting mass for a star whose core becomes a black hole; NASA pages differ (15 vs 20), and Gaia BH3 shows the models are still being revised.","to leave a black hole behind, a star probably needs around twenty times the Sun's mass, or more. Exactly where that line sits is still being studied.",["nasa_bh_types","imagine_stars","imagine_sn"],[
 ev("nasa_bh_types",0,"If it had around 20 times the Sun’s mass or more, the star’s core collapses into a stellar-mass black hole.","direct","Around 20 solar masses or more."),
 ev("imagine_stars",1,"Only stars with more than 20 times the mass of the Sun will become black holes.","direct","Same threshold, older NASA page."),
 ev("imagine_sn",2,"if the original star is very massive indeed (say 15 or more times the mass of our Sun), even the neutrons cannot survive the core collapse...and a black hole forms.","partial","A sibling NASA page gives 15 — the line is uncertain, hence hedged wording.","minor")],
 status="contested", note="Hedged in narration ('probably', 'around', 'still being studied')."))
C.append(claim("C12_supergiant","When core hydrogen runs out the core contracts and heats while the outer layers swell; a high-mass star becomes a red supergiant.","When the hydrogen in its core runs out, gravity squeezes the core, the core heats up, and the outer layers swell. The star becomes a red supergiant.",["imagine_stars","nasa_stars"],[
 ev("imagine_stars",0,"First, the outer layers swell out into a giant star, but even bigger, forming a red supergiant.","direct","High-mass stars become red supergiants."),
 ev("imagine_stars",0,"Its inner layers start to collapse, which squishes the core, increasing the pressure and temperature in the core of the star. While the core collapses, the outer layers of material in the star to expand outward.","direct","Core squeezed and heated, outer layers expand."),
 ev("nasa_stars",1,"At the beginning of the end of a star’s life, its core runs out of hydrogen to convert into helium.","direct","Trigger: core hydrogen runs out.")]))
C.append(claim("C13_chain","Massive stars fuse helium to carbon, carbon to neon, and further elements (oxygen, neon, magnesium, silicon) up to iron; each new fuel lasts less time and the final silicon-to-iron stage ends in days.","Helium fuses into carbon. Carbon into neon. Then oxygen, then silicon. Each new fuel buys the star less time than the one before. And when silicon finally fuses into iron, the star runs out of fuel in a matter of days.",["nasa_stars","imagine_stars"],[
 ev("nasa_stars",0,"Fusion converts carbon into heavier elements like oxygen, neon, and magnesium, which will become future fuel for the core. For the largest stars, this chain continues until silicon fuses into iron.","direct","The chain up to silicon to iron."),
 ev("nasa_stars",0,"each new fuel buys it less and less time","direct","Each fuel buys less time."),
 ev("nasa_stars",0,"By the time silicon fuses into iron, the star runs out of fuel in a matter of days.","direct","Final stage lasts days."),
 ev("imagine_stars",1,"Then, fusion of helium into carbon begins in the core.","direct","Helium to carbon."),
 ev("imagine_stars",1,"it will become hot and dense enough to fuse carbon into neon","direct","Carbon to neon.")]))
C.append(claim("C14_iron","Fusing iron requires energy instead of releasing it, so a core of iron can no longer support the star against gravity.","Iron is a dead end. Fusing iron doesn't release energy; it costs energy. So nothing is left to push back against gravity.",["imagine_stars","chandra_casa_life","nasa_stars"],[
 ev("imagine_stars",0,"fusing iron requires an input of energy, rather than producing excess energy. With a core full of iron, the star will lose the fight against gravity.","direct","Iron costs energy; the star loses to gravity."),
 ev("chandra_casa_life",1,"further nucleosynthesis would consume rather than produce energy, so gravity then caused the star to implode","direct","Independent Chandra page."),
 ev("nasa_stars",2,"doing so requires energy instead of releasing it","direct","Third NASA page.")]))
C.append(claim("C15_collapse","The final core collapse happens in less than a second and the core temperature rises above 100 billion degrees.","In less than a second, the core collapses. Its temperature soars past one hundred billion degrees.",["imagine_sn","imagine_stars"],[
 ev("imagine_sn",0,"In less than a second, the star begins the final phase of gravitational collapse. The core temperature rises to over 100 billion degrees as the iron atoms are crushed together.","direct","Under one second; over 100 billion degrees."),
 ev("imagine_stars",1,"The core temperature rises to over 100 billion degrees as the iron atoms are crushed together.","direct","Same statement on sibling page (same institution).")],
 status="verified", note="Both pages are NASA HEASARC; counted as one institutional source."))
C.append(claim("C16_rebound","The collapsing iron core rebounds, sending a shock wave outward through the star: a supernova; the core survives as a neutron star or black hole.","Then the core rebounds, and a shock wave races outward through the star. That is a supernova.",["nasa_stars","nasa_bh_types"],[
 ev("nasa_stars",0,"The star’s iron core collapses until forces between the nuclei push the brakes, then it rebounds. This change creates a shock wave that travels outward through the star. The result is a huge explosion called a supernova.","direct","Rebound, shock wave, supernova."),
 ev("nasa_stars",0,"The core survives as an incredibly dense remnant, either a neutron star or a black hole.","direct","Remnant types.")]))
C.append(claim("C17_outshine","A supernova often briefly outshines an entire galaxy before fading over several weeks or months.","For a while, this one dying star can outshine its entire galaxy, before fading over weeks or months.",["esahubble_sn"],[
 ev("esahubble_sn",0,"Supernovae are extremely luminous and cause a burst of radiation that often briefly outshines an entire galaxy, before fading from view over several weeks or months.","direct","Direct statement.")]))
C.append(claim("C18_crab","In 1054 Chinese astronomers recorded a 'guest star' visible in daytime for nearly a month; it was the supernova that produced the Crab Nebula, a six-light-year-wide remnant.","In the year ten fifty-four, Chinese astronomers recorded a 'guest star' visible in the daytime sky for nearly a month. ... the Crab Nebula: the expanding wreckage of that explosion, six light-years wide.",["nasa_crab"],[
 ev("nasa_crab",0,"In 1054, Chinese astronomers took notice of a “guest star” that was, for nearly a month, visible in the daytime sky. The “guest star” they observed was actually a supernova explosion, which gave rise to the Crab Nebula, a six-light-year-wide remnant of the violent event.","direct","All parts of the claim.")]))
C.append(claim("C19_casa","Chandra's X-ray image of Cassiopeia A maps silicon, sulfur, calcium and iron ejected by the supernova.","This is Cassiopeia A, the remains of an exploded star, mapped in X-rays. The colors show silicon, sulfur, calcium and iron, thrown out into space.",["chandra_casa_life"],[
 ev("chandra_casa_life",0,"A new image from NASA's Chandra X-ray Observatory shows the location of different elements in the remains of the explosion: silicon (red), sulfur (yellow), calcium (green) and iron (purple).","direct","Elements mapped in the image.")]))
C.append(claim("C20_elements","All the oxygen in the Solar System comes from exploding massive stars, as does about half the calcium and about 40% of the iron; calcium helps form bones.","all the oxygen in our solar system came from exploding massive stars, along with about half the calcium and about forty percent of the iron. Some of the calcium in your bones came from these explosions.",["chandra_casa_life","nasa_stars"],[
 ev("chandra_casa_life",0,"All of the oxygen in the Solar System comes from exploding massive stars. About half of the calcium and about 40% of the iron also come from these explosions","direct","Element fractions as stated by NASA/Chandra."),
 ev("chandra_casa_life",0,"calcium helps form and maintain healthy bones and teeth","direct","Calcium in bones."),
 ev("chandra_casa_life",0,"Oxygen is the most abundant element in the human body (about 65% by mass)","direct","Supports the Short's line that oxygen is about two thirds of body weight."),
 ev("nasa_stars",1,"Material cast into the cosmos by supernovae and other stellar events will enrich future molecular clouds","context","Supernova material spreads into future clouds.")]))
C.append(claim("C21_remnant","If the star was near the supernova threshold the core becomes a city-sized superdense neutron star; with around 20+ solar masses it becomes a stellar-mass black hole.","If the star was near the lower limit, it becomes a neutron star, about the size of a city. If the star was heavy enough, nothing can stop the collapse.",["nasa_bh_types","imagine_sn"],[
 ev("nasa_bh_types",0,"If it was near the threshold, it creates a city-sized, superdense neutron star.","direct","City-sized neutron star."),
 ev("imagine_sn",1,"even the neutrons cannot survive the core collapse...and a black hole forms","direct","For heavy enough stars nothing halts collapse.")]))
C.append(claim("C22_horizon","A black hole is so dense that at its event horizon nothing, not even light, can escape.","its gravity is so strong that not even light can escape. That boundary is the event horizon.",["nasa_bh","eso_eht"],[
 ev("nasa_bh",0,"A black hole is so dense that gravity just beneath its surface, the event horizon, is strong enough that nothing – not even light – can escape.","direct","Direct statement."),
 ev("eso_eht",1,"a completely dark object from which light cannot escape","direct","Independent ESO statement.")]))
C.append(claim("C23_eht","In April 2019 the Event Horizon Telescope revealed the first image of a black hole's shadow, in galaxy M87; that black hole has 6.5 billion solar masses and lies 55 million light-years away.","This is the first image of a black hole's shadow, from the Event Horizon Telescope in 2019. That one is a giant in the galaxy M87, six and a half billion times the Sun's mass. Black holes left behind by dying stars are far smaller.",["eso_eht","nasa_bh_types"],[
 ev("eso_eht",0,"unveiling the first direct visual evidence of a supermassive black hole and its shadow","direct","First image of a black hole's shadow."),
 ev("eso_eht",0,"This black hole resides 55 million light-years from Earth and has a mass 6.5 billion times that of the Sun","direct","Mass and distance."),
 ev("eso_eht",0,"10 April 2019","context","Release date of eso1907."),
 ev("nasa_bh_types",1,"The masses of these newly born objects can range from a few to hundreds of times the Sun’s mass","direct","Star-made black holes: a few to hundreds of solar masses, far below 6.5 billion.")]))
C.append(claim("C24_binaries","Nearly all stellar-mass black holes observed so far were found paired with stars; in X-ray binaries the black hole pulls gas off the star into a disk hot enough to emit X-rays.","Nearly every black hole left behind by a dead star that we've found so far is paired with a living star. ... a black hole pulls gas off its companion, into a disk hot enough to glow in X-rays.",["nasa_bh_types"],[
 ev("nasa_bh_types",0,"Nearly all the stellar-mass black holes observed so far have been found because they’re paired with stars.","direct","States the claim directly."),
 ev("nasa_bh_types",0,"the black hole pulls gas off the star into a disk that heats up enough to produce X-rays","direct","X-ray binaries mechanism.")]))
C.append(claim("C25_cygx1","A 2021 study (Miller-Jones et al., Science) found the black hole in the X-ray binary Cygnus X-1 has 21.2 ± 2.2 solar masses.","A 2021 study puts that black hole at about twenty-one times the mass of the Sun.",["arxiv_cygx1","esa_gaiabh3"],[
 ev("arxiv_cygx1",0,"this implies a black hole mass of $21.2\\pm2.2$ solar masses","direct","Peer-reviewed mass estimate."),
 ev("arxiv_cygx1",0,"black hole X-ray binary Cygnus X-1","direct","Cyg X-1 is an X-ray binary (supports the gas-pulling scene)."),
 ev("esa_gaiabh3",1,"a black hole in an X-ray binary in the Cygnus constellation (Cyg X-1), whose mass is estimated to be around 20 times that of the Sun","partial","ESA gives ~20; consistent within uncertainty.","minor")]))
C.append(claim("C26_gaiabh3","In April 2024 ESA's Gaia data revealed Gaia BH3, a dormant black hole of about 33 solar masses, found from the wobble of an old giant star 1,926 light-years away; the first stellar-origin black hole this big seen in the Milky Way.","in 2024, the Gaia mission noticed an old star wobbling around something unseen, less than two thousand light-years away. It is a black hole about thirty-three times the Sun's mass, the biggest star-made black hole found in our galaxy when it was announced.",["esa_gaiabh3"],[
 ev("esa_gaiabh3",0,"A large black hole, with a mass of nearly 33 times the mass of the Sun, was hiding in the constellation Aquila, less than 2000 light-years from Earth. This is the first time a black hole of stellar origin this big has been spotted within the Milky Way.","direct","Mass, distance, record."),
 ev("esa_gaiabh3",0,"their attention fell on an old giant star in the constellation Aquila","direct","An old star."),
 ev("esa_gaiabh3",0,"By analysing in detail the wobble in the star’s path","direct","Found by the star's wobble."),
 ev("esa_gaiabh3",0,"Sleeping giant surprises Gaia scientists","context","Article title; the page is dated 16/04/2024 (2024).")]))
C.append(claim("C27_n6946","N6946-BH1, a ~25 solar-mass red supergiant, had a weak outburst in 2009 and then largely disappeared in optical light; it was proposed as a failed supernova (direct collapse to a black hole), but JWST data show the earlier observations blend at least 3 sources and the interpretation remains debated.","In 2009, a red supergiant about twenty-five times the Sun's mass, in another galaxy, flared weakly and then seemed to disappear. One explanation is a failed supernova ... newer telescope data complicate that picture, and astronomers are still debating it.",["arxiv_n6946","arxiv_n6946_jwst","gsfc_vanished"],[
 ev("arxiv_n6946",0,"This $\\sim 25~M_{\\odot}$ red supergiant experienced a weak $\\sim 10^{6}~L_{\\odot}$ optical outburst in 2009 and is now at least 5 magnitudes fainter than the progenitor in the optical","direct","~25 solar-mass red supergiant, weak 2009 outburst, then optical disappearance."),
 ev("arxiv_n6946_jwst",1,"all previous observations of BH1 (pre- and post-disappearance) are actually a blend of at least 3 sources","direct","Newer JWST data complicate the picture."),
 ev("gsfc_vanished",2,"If confirmed, this would be the first time anyone has witnessed the birth of a black hole and the first discovery of a failed supernova.","direct","Status: unconfirmed candidate.")],
 status="contested", note="Narration hedges: 'seemed to', 'one explanation', 'still debating'."))
C.append(claim("C28_enrich","Material cast out by supernovae enriches future molecular clouds and is incorporated into the next generation of stars.","The gas the star threw away drifts back out, and enriches the next clouds.",["nasa_stars","chandra_sn_guide"],[
 ev("nasa_stars",0,"Material cast into the cosmos by supernovae and other stellar events will enrich future molecular clouds and become incorporated into the next generation of stars.","direct","States the claim directly."),
 ev("chandra_sn_guide",1,"supernovas are the primary means for seeding the galaxy with many elements","direct","Independent Chandra page.")]))
# fix sources for C28 (added after)
for c in C:
    if c["id"]=="C28_enrich": c["sources"]=[{"title":SRC[s][0],"url":SRC[s][1],"type":SRC[s][2],"accessed":"2026-10-31"} for s in ["nasa_stars","chandra_sn_guide"]]
json.dump({"claims":C},open(f"{P}/facts.json","w"),indent=2,ensure_ascii=False)
with open(f"{P}/facts.md","w") as f:
    f.write("# Facts\n\n| id | status | claim | sources |\n|---|---|---|---|\n")
    for c in C: f.write(f"| {c['id']} | {c['status']} | {c['text']} | {'; '.join(s['url'] for s in c['sources'])} |\n")
print(len(C),"claims ok")
