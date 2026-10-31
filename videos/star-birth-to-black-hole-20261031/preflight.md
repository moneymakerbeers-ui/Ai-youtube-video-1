# Preflight — star-birth-to-black-hole-20261031 (2026-10-31)

| item | status | evidence (this run) | fallback |
|---|---|---|---|
| engine (Chromium renderer, ffmpeg, python, node) | AVAILABLE | `tools/doctor.py` READY; `npm run typecheck` ok; `npm run selftest` SELFTEST PASSED (30 rules) | — |
| fonts in library/fonts | Inter present as system font (fc-list); doctor flags library/fonts | `fc-list` lists Inter, Inter Display, JetBrains Mono | browser font stack named in style tokens |
| Higgsfield MCP | AVAILABLE | `balance` → 46.97 credits, plan pro; private workspace f287a423… | code graphics + retrieved telescope images |
| Higgsfield download of results | AVAILABLE | curl of a Higgsfield CloudFront preview → HTTP 200, 52 KB mp3, ffprobe 3.24 s | — |
| Knox voice | AVAILABLE (preset) | `list_voices` → Knox, preset, id 195e386a-cb61-5c1b-a53b-0e2f0669c408; `text2speech_v2` supports variant `elevenlabs` | — |
| ElevenLabs direct API | UNAVAILABLE | `ELEVENLABS_API_KEY` not set; doctor `--net` api.elevenlabs.io HTTP 405 | Knox via Higgsfield (ElevenLabs engine) = stack B |
| research (web fetch) | AVAILABLE | NASA images API, esawebb.org, esahubble.org, eso.org, chandra.harvard.edu → HTTP 200 | — |
| retrieved telescope imagery | AVAILABLE | same as above; licences to be saved per asset | generated illustration |
| PyPI / npm | AVAILABLE | `pip download faster-whisper` ok; npm install ok | — |
| terms (Higgsfield / ElevenLabs commercial use) | unverified | not checked yet; creator confirms their plan allows commercial use | — |

## Prices (free previews, see prices.json)
- Knox TTS (text2speech_v2/elevenlabs): 0.30 cr / 91 chars, 2.85 cr / 919 chars (≈0.0031 cr/char).
- Images 16:9 2k: gpt_image_2_5 high 2.75 · medium 1.0 · nano_banana_2 2.0 · cinematic_studio_2_5 2.0.
- Credit→dollar rate unknown (`dollarsPerCredit: null`).

## Voice stack decision
B — Knox through Higgsfield `text2speech_v2` variant `elevenlabs`, takes registered with `voice.py --stack file`. Requested by the creator. Spend-gated in Higgsfield credits.
flite (D) is used only for the free preview / alignment reference; never shipped as the narrator without the creator's explicit yes.

## Quality limits on this machine
- No direct ElevenLabs key: voice settings (stability/style) cannot be set; delivery is steered by text punctuation and take boundaries only.
- Alignment of a non-flite voice with the built-in `dtw` engine is APPROXIMATE (STATUS.md §4.1).
- Render is CPU Chromium screenshots at 1080p (4 cores): expect long render times; 30 fps chosen.
