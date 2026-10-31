# Install and first run (v3)

Everything below was run exactly as written on the machine described in the last section. Nothing here needs an account: the free path (local voice, code-drawn graphics) works without any key.

## 1. What you need
| need | tested version | check |
|---|---|---|
| Linux x86-64 (macOS and Windows are **untested**) | Ubuntu-family, kernel 6.18 | `uname -a` |
| Node.js | 22.23.4 (`engines`: ≥ 22) | `node -v` |
| Python | 3.13.18 | `python3 -V` |
| ffmpeg + ffprobe, built with `libx264`, `aac` and (for the free voice) `libflite` | 6.1.1 | `ffmpeg -version` |
| Chromium, installed by Playwright (the renderer) | 153.0.8010.12 with Playwright 1.63.0 | `python3 tools/doctor.py` |
| 2 GB free disk and 2 CPU cores (more cores render faster: `--workers N`) | | |

Exact npm pins (`package.json`): esbuild 0.28.2 · playwright 1.63.0 · zod 3.25.76 · tsx 4.23.12 · typescript 6.0.3 · @types/node 26.6.3. Python pins (`requirements.txt`): numpy 2.5.3 · scipy 1.18.1 · pillow 12.3.0 · pytest 9.1.1. The registry was not reachable from the build sandbox, so no lock file could be generated there: run `npm install` once and commit the `package-lock.json` it creates; until then the exact pins in `package.json` are the reproducibility mechanism.

## 2. Install
```bash
unzip youtube-system-v3.1-fixed.zip && cd youtube-system
npm install                                   # exact pins from package.json
npx playwright install chromium               # the renderer's browser (a download)
python3 -m venv .venv && . .venv/bin/activate # optional; prefer a virtual environment; do not modify system Python instead
python3 -m pip install -r requirements.txt
python3 tools/doctor.py                       # AVAILABLE / MISSING / UNTESTED / BLOCKED, with evidence; exit 3 = something required is missing
```
`doctor.py` never reports something AVAILABLE from memory: each line is a command that just ran. A missing ffmpeg filter, Chromium or Python module is named with the command that fixes it. The three live services (ElevenLabs, Higgsfield, YouTube) are reported **UNTESTED** until a call succeeds.

## 3. Check the install (about 14 minutes on 2 CPU cores: v3.1 pytest 12 min 57 s; no network, no spend)
```bash
npm test          # typecheck + schema self-test + 84 engine unit tests + the Python suite (89 tests) (all nine acceptance tests are in it)
```
or piece by piece: `npm run typecheck`, `npm run selftest`, `npm run test:engine`, `npm run test:py`. `tests/.work/` is scratch space the tests create and may delete.

## 4. The free end-to-end demo
```bash
# This creates a fresh demo without deleting any other video.
DEMO_DIR="videos/demo-$(date +%Y%m%d-%H%M%S)"
cp -r examples/smoke "$DEMO_DIR"
python3 tools/pipeline.py run --project "$DEMO_DIR" --size 640x360 --auto-downgrade
```
It narrates four short scenes with the free local voice, aligns the final audio, renders the 16:9 video and the recomposed 9:16 Short from the same `scenes.json` (one truthful morph, a dissolve, two cuts), then runs media QA and motion QA on both files and writes `$DEMO_DIR/review/production-report.md`. Outputs: `$DEMO_DIR/out/full-video.mp4` (640×360), `$DEMO_DIR/out/short-01.mp4` (360×640), `out/captions.srt`. The same run is shipped in `demo/` of this archive. Add `--size 1920x1080` for full size.

## 5. Make a real video in Claude Code
```bash
cd youtube-system && claude
```
then type the one line:
```
/make <VIDEO_IDEA>
```
(`/make resume` continues an interrupted video: it checks the spend ledger first and never repeats a paid request.) Optional: copy `.claude/settings.example.json` to `.claude/settings.json` to pre-approve the build and QA commands; it denies `sudo` and reading `.env`. Optional: copy `channel.example.md` to `channel.md` to fix brand constants. The system asks one question per video (preview + per-service spend) and otherwise decides, logs and continues.

## 6. Paid services (all optional)
- **ElevenLabs** narration: choose the voice once in the video's `config.json`: `"voice": {"elevenlabs": {"voiceId": "<ID>", "model": "eleven_multilingual_v2"}}` (stage 03 writes it; `--voice-id` still overrides). `export ELEVENLABS_API_KEY=...` (presence is checked, the key is never printed or logged). The creator's approval at the spend gate sets a character ceiling (`ledger.py approve --service elevenlabs --ceiling N --unit chars`). `pipeline.py --stack auto` uses it only when both exist; otherwise it falls back to the free voice and says so in the report.
- **Higgsfield** images or voice: reached through the Higgsfield MCP tools in Claude Code; every call is wrapped in `tools/ledger.py` (price first, per-service ceiling, resumable).
- **YouTube**: there is no upload step. The system produces the files plus `youtube.md`; publish in Studio.
What is TESTED, UNTESTED and BLOCKED is in `docs/STATUS.md`.

## 7. Layout
```
CLAUDE.md                    the operating rules (read first)         .claude/commands/   /make and stages 00-07
engine/                      the renderer: scene graph → Chromium frames → ffmpeg
tools/                       every CLI (doctor, pipeline, voice, ledger, preview, qa_media, qa_motion, …)
schema/                      typed data (zod) and cross-file validation      reference/   grammar, QA gates, presets, voice direction
library/                     shared fonts (OFL), style bibles, assets, thresholds, lessons
examples/smoke/              the demo project            demo/        its shipped output (MP4s, QA reports, production report)
tests/                       pytest suite, engine unit tests, a mock ElevenLabs server
docs/STATUS.md               TESTED / UNTESTED / BLOCKED        docs/V3-REPORT.md   what changed and how it was tested
videos/<slug>/               one video: config, facts, scenes, assets, audio, render/, qa/, review/, out/
```

## 8. Environment variables
`ELEVENLABS_API_KEY` (paid voice) · `ALIGN_REF_VOICE` (the flite voice used as the alignment reference, default `slt`; it must match the voice that narrated) · `PLAYWRIGHT_BROWSERS_PATH` (where Chromium lives) · `QA_FAULT` and `PAID_FAULT` (fault injection used by the tests; never set them in production).

## 9. Where it was tested
One sandbox: Linux, 2 CPUs, node 22.23.4, Python 3.13.18, ffmpeg 6.1.1, Chromium 153.0.8010.12, no access to npm, PyPI, ElevenLabs, Higgsfield or YouTube during the run. Rendering is reproducible on those versions with the same worker count (two renders of one plan are byte-identical, tested for the long video and for a Short; the default is 2 workers). A different worker count, Chromium or ffmpeg may give different bytes (text-edge pixels) and slightly different QA numbers.
