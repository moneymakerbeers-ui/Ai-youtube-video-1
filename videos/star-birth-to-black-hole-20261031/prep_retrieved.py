#!/usr/bin/env python3
"""prep_retrieved.py — crop/resize the retrieved telescope images into project assets + licence evidence (stage 02)."""
import json, os, sys, shutil
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]   # download folder
LIC = sys.argv[2]   # licence-page text folder
# id: (file, crop box as fractions (l,t,r,b) or None, out size, credit, license, page, licence-text key, image-page key, what it shows)
A = {
 "r_pillars": ("weic2216b.jpg", (0.0, 0.19, 1.0, 0.515), (2560, 1440), "NASA, ESA, CSA, STScI; J. DePasquale, A. Koekemoer, A. Pagan (STScI)", "CC BY 4.0", "https://esawebb.org/images/weic2216b/", "webb_copyright", "img_weic2216b", "Webb NIRCam: Pillars of Creation (heads of the pillars)"),
 "r_carina": ("weic2205a.jpg", (0.0, 0.014, 1.0, 0.986), (2560, 1440), "NASA, ESA, CSA, and STScI", "CC BY 4.0", "https://esawebb.org/images/weic2205a/", "webb_copyright", "img_weic2205a", "Webb NIRCam: 'Cosmic Cliffs' edge of NGC 3324 in Carina, a molecular-cloud star-forming region"),
 "r_rhooph": ("weic2316a.jpg", (0.0, 0.12, 1.0, 0.72), (2560, 1440), "NASA, ESA, CSA, STScI, K. Pontoppidan (STScI), A. Pagan (STScI)", "CC BY 4.0", "https://esawebb.org/images/weic2316a/", "webb_copyright", "img_weic2316a", "Webb NIRCam: Rho Ophiuchi, red bipolar jets from young stars"),
 "r_helix": ("heic0307a.jpg", None, (2000, 2000), "NASA, NOAO, ESA, the Hubble Helix Nebula Team, M. Meixner (STScI), and T.A. Rector (NRAO)", "CC BY 4.0", "https://esahubble.org/images/heic0307a/", "hubble_copyright", "img_heic0307a", "Helix Nebula: shed outer layers around a white dwarf"),
 "r_crab": ("heic0515a.jpg", None, (2400, 2400), "NASA, ESA and Allison Loll/Jeff Hester (Arizona State University); acknowledgement Davide De Martin (ESA/Hubble)", "CC BY 4.0", "https://esahubble.org/images/heic0515a/", "hubble_copyright", "img_heic0515a", "Hubble mosaic of the Crab Nebula (remnant of SN 1054)"),
 "r_sn_hubble": ("opo9919i.jpg", (0.0, 0.42, 1.0, 0.9825), (2560, 1440), "NASA/ESA, The Hubble Key Project Team and The High-Z Supernova Search Team", "CC BY 4.0", "https://esahubble.org/images/opo9919i/", "hubble_copyright", "img_opo9919i", "Hubble: Supernova 1994D (bright point, lower left) in galaxy NGC 4526"),
 "r_n6946": ("opo1719b.jpg", None, (1800, 1200), "NASA, ESA, and C. Kochanek (OSU)", "CC BY 4.0", "https://esahubble.org/images/opo1719b/", "hubble_copyright", "img_opo1719b", "Hubble before (2007) / after (2015) images of N6946-BH1"),
 "r_eht": ("eso1907a.jpg", (0.04, 0.0, 0.96, 0.894), (2560, 1440), "EHT Collaboration", "CC BY 4.0", "https://www.eso.org/public/images/eso1907a/", "eso_copyright", "img_eso1907a", "Event Horizon Telescope image of the M87* black hole shadow (supermassive)"),
 "r_gaiabh3_art": ("eso2408a.jpg", (0.0, 0.0, 1.0, 0.8164), (2560, 1440), "ESO/L. Calçada/Space Engine (spaceengine.org)", "CC BY 4.0", "https://www.eso.org/public/images/eso2408a/", "eso_copyright", "img_eso2408a", "ARTIST'S IMPRESSION of the Gaia BH3 system (illustration, not a photograph)"),
 "r_casa": ("casa_life_4k.jpg", None, (864, 864), "NASA/CXC/SAO", "NASA/Chandra: no copyright asserted, credit requested", "https://chandra.harvard.edu/photo/2017/casa_life/", "chandra_use", "img_casa", "Chandra X-ray element map of Cassiopeia A: Si red, S yellow, Ca green, Fe purple"),
 "r_cygx1_art": ("cygx1_ill.jpg", (0.0, 0.103, 1.0, 0.897), (1728, 972), "Illustration: NASA/CXC/M.Weiss", "NASA/Chandra: no copyright asserted, credit requested", "https://chandra.harvard.edu/photo/2011/cygx1/", "chandra_use", "img_cygx1", "ILLUSTRATION of Cygnus X-1: black hole with accretion disk pulling gas from a blue supergiant companion"),
 "r_sun": ("sdo_0304.jpg", (0.039, 0.029, 0.961, 0.951), (1888, 1888), "NASA/SDO and the AIA science team", "NASA SDO: not copyrighted unless noted, attribution requested", "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_2048_0304.jpg", "sdo_rules", "sdo_rules", "SDO/AIA 304 Å image of the Sun, 2026-10-31 13:09 UT (timestamp cropped out)"),
}
out = {}
for aid, (f, box, size, credit, lic, page, lickey, imgkey, shows) in A.items():
    im = Image.open(os.path.join(SRC, f)).convert("RGB")
    if box:
        W, H = im.size
        im = im.crop((round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)))
    im = im.resize(size, Image.LANCZOS) if im.size != size else im
    dst = os.path.join(HERE, "assets", f"{aid}.jpg")
    im.save(dst, quality=92, subsampling=0)
    lf = os.path.join(HERE, "assets", "_licenses", f"{aid}.txt")
    with open(lf, "w") as o:
        o.write(f"asset: {aid}\nsource page: {page}\nsource file: {f}\ncredit: {credit}\nlicense: {lic}\nshows: {shows}\nretrieved: 2026-10-31 (curl)\nprocessing: crop {box}, resize to {size}\n\n===== licence / usage page text =====\n")
        o.write(open(os.path.join(LIC, f"{lickey}.txt")).read())
        if imgkey != lickey:
            o.write("\n\n===== image page text (credit line) =====\n"); o.write(open(os.path.join(LIC, f"{imgkey}.txt")).read())
    out[aid] = {"file": f"assets/{aid}.jpg", "width": size[0], "height": size[1], "credit": credit, "license": lic, "page": page, "shows": shows}
    print(aid, im.size)
json.dump(out, open(os.path.join(HERE, "assets", "retrieved.json"), "w"), indent=1, ensure_ascii=False)
