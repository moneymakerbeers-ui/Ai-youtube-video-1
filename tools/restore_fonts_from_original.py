#!/usr/bin/env python3
"""OPTIONAL: Restore a user's own fonts from their original system ZIP.

The fixed archive deliberately contains no font binaries. The default project
uses the browser's sans-serif fallback. To reproduce the v3.1 Inter typography,
run this with the ORIGINAL archive you already own (the script does not download
or distribute fonts), then update the project's style-tokens.json fonts.files.

Usage: python3 tools/restore_fonts_from_original.py /path/to/youtube-system-v3.1.zip
"""
import argparse
from pathlib import Path
from zipfile import ZipFile

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('archive', type=Path)
a = ap.parse_args()
repo = Path(__file__).resolve().parent.parent
prefix = 'youtube-system/library/fonts/'
with ZipFile(a.archive) as z:
    names = [n for n in z.namelist() if n.startswith(prefix) and n.lower().endswith(('.otf','.ttf','.woff','.woff2'))]
    if not names:
        ap.error('No font files at the expected location in the original archive')
    for name in names:
        rel = Path(name).relative_to(prefix)
        if any(p in ('..','') for p in rel.parts):
            ap.error('unsafe font path')
        dest = repo / 'library' / 'fonts' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(name))
print(f'Restored {len(names)} locally supplied font file(s). Update style tokens to reference them if desired.')
