# STATUS — what is real, what was tested, what was not (v3.1, 30 Oct 2026)

Read this before promising anyone anything. **TESTED** = a command in a test run in the build sandbox succeeded and the result was checked (the test is named). **UNTESTED** = the code exists but was never run against the real thing. **BLOCKED** = something in the environment prevented it. Nothing below is rounded up.

## 1. Where the system stands
- **v2 was a prototype in prose**: documents, a schema and some scripts, with no render engine installed, a QA tool that could pass on a broken ffmpeg, blanket QA allowances, and no way to resume a paid request safely.
- **v3 is a production-capable engine on the free path**: from one scene file it renders a reproducible 16:9 video and recomposed 9:16 Shorts, narrates them with a free local voice, aligns the final audio, fails closed in QA, and resumes without repeating work or paid requests. Every claim in this file has a named test.
- **v3 is not yet production-proven**: no real 6–9 minute video with real photographic/generated assets and a paid natural voice has been produced with it. The first real video is the shakedown: expect to calibrate thresholds (`library/thresholds.json`) and to find things only real material shows. The demos here are a 12.7-second synthetic video plus a 14.2-second Short (`demo/`).
- Quality that no machine here can judge — whether a story is good, a voice sounds human, a transition feels right — is listed per run under "a person still has to look at".

## 2. Live integrations
| integration | status | what was actually run | what was NOT run |
|---|---|---|---|
| **ElevenLabs** text-to-speech, history lookup (resume) | **TESTED against a local mock only** (v3.1: voice id and model from `config.json`, per-scene emotion compiled into request shape for v2- and v3-class models; checked by `test_f_voice_direction.py`) | `tests/mock_elevenlabs.py` is an HTTP server I wrote that imitates `POST /v1/text-to-speech/{voice}`, `GET /v1/history`, `GET /v1/history/{id}/audio`. Tests A8/A9 drive the adapter against it: one request per item, a crash after the provider accepted, a crash before the request, a re-run that pays nothing, refusal without approval, over the ceiling and with a missing key | the real service: real authentication, errors, rate limits, response headers, the real shape and pagination of the history endpoint, voice and model names, audio quality, cost per character. **Live ElevenLabs is UNTESTED.** |
| **ElevenLabs** forced alignment | **UNTESTED** | the adapter code exists (`tools/align.py --engine elevenlabs`); it needs a key and network | any call |
| **Higgsfield** images (v3.1), voice, credits | **images: generation TESTED with 3 real jobs; download BLOCKED; voice UNTESTED** | v3.1 ran the real flow once: approval with a 10-credit ceiling → `ledger intent → submitted(job id) → done` for 3 `gpt_image_2_5` images (0.75 credits, status in `ledger.py status`), all completed. The tool's `get_cost` preflight returned 2.75 credits for high/2k. | **the sandbox could not download the result** (CloudFront refused: network allow-list), so no real generated image went through the renderer here; the creator or the linked computer must supply the files. A bare call defaults to `quality: low`, `resolution: 1k` (a draft): stage 02 now requires explicit high/2k. Not verified: crash-recovery of a job by id on the live service; whether price previews match debits to the cent; Higgsfield voice |
| **YouTube** | **UNTESTED, and there is no upload step by design** | thumbnails are checked against 1280×720 and 2 MB, the documented upload limits as read on 29–30 Oct 2026; chapter timestamps are checked against the probed duration | any contact with YouTube or Studio; the altered/synthetic-content wording in `disclosure.md` comes from reading documentation, not from Studio |
| **Whisper** alignment | **NOT IMPLEMENTED** | `--engine whisper` exits 3 BLOCKED with that message; `auto` never selects it (test: `test_e_regressions_and_assets.py`) | — |
| music beds (`mix.py --music`) | **UNTESTED** | the code path exists (licence file required, looped, ducked) | no test runs it |

Network: the build sandbox's allow-list refused npm, PyPI, ElevenLabs, Higgsfield and YouTube hosts (BLOCKED). That is why no lock file was generated, why Remotion was not used (it could not be installed here), and why nothing live was tested.

## 3. Components (all run in `npm test`)
| component | status | evidence |
|---|---|---|
| renderer: scene graph → Chromium (Playwright) → ffmpeg, H.264/AAC, BT.709 | TESTED | every pipeline test; `test_d…determinism` (a second render of the long video and of a Short is byte-identical to the first); `test_d…colours_survive_encoding` |
| 8 transition operators | TESTED (maths and real frames) | `tests/engine/transitions.test.ts`; `test_c_operator_matrix` renders 16 transitions and runs motion QA on the real frames |
| raster images through manifest → plan → pixels, both layouts | TESTED (flat colours; v3.1: procedural photographic-style plates) | `test_e…raster_image_asset_renders_in_both_layouts`; `test_g_image_pipeline.py` (9 tests) |
| layered image scene: transparent cut-out over a plate, camera move, parallax (far layer moves less), image-to-image `nested_scale`, 16:9 and recomposed 9:16, media + motion QA on the delivered frames | TESTED on SYNTHETIC plates (not model-generated images) | `test_g_image_pipeline.py`; it found and fixed two real bugs (instant-entrance plate popping in a dissolve; declared fade counted as codec noise) |
| voice direction execution (v2/v3 model families), continuity check, config-resolved voice id | TESTED request shape on a mock; real voice quality UNTESTED | `test_f_voice_direction.py` (8 tests) |
| code visuals (flow, aspect_frame, bars, counter, wave, arrow, grid), text, captions | TESTED | the smoke project and the matrix |
| media QA, fail-closed | TESTED | A1–A3 (`test_a1_a2_a3_qa_fails.py`) |
| motion QA inside transitions | TESTED | A6 (`test_a6_a7_…`), the matrix |
| plan-aware allow-lists, no blanket allowances | TESTED | `test_d…allow_lists…`, A2, A3 |
| schema and cross-file validation, script lint | TESTED | A4, `selftest` |
| evidence check (snapshots, hashes, quotes, numbers) | TESTED | `test_a4…evidence…`, `…number_the_narration_speaks…`, `…model_processed…` |
| per-service spend gate, ledger, resume | TESTED (mock provider) | A8, A9 |
| free voice, assembly, DTW alignment, each Short's own audio and alignment | TESTED for the flite voice | A5, the smoke project |
| auto-downgrade of a failing transition | TESTED | `test_b…downgrade…` |
| creative preview gate | TESTED | `test_b…preview…` |
| production report, thumbnails, project scaffold | TESTED | `test_b…` |
| doctor (honest inventory) | TESTED | A9 |
| two aspect ratios from one scene file, resumable pipeline | TESTED | A7 |
| `config.fps`, default 30 | TESTED | `test_e…config_fps…` |

## 4. Known limits (do not discover these by surprise)
1. **Alignment.** The free `dtw` engine aligns against a flite reference and is trustworthy only when the narrator *is* that flite voice (`ALIGN_REF_VOICE` must match). With another voice and no ElevenLabs key it still runs but marks itself APPROXIMATE (scene and sentence boundaries hold, word boundaries can be off by hundreds of ms). ElevenLabs forced alignment is UNTESTED. Whisper is not implemented.
2. **The free voice is robotic.** It exists so everything downstream runs with no account. Never publish it as a final narrator; the report says which voice made the file.
3. **Reviews are only as independent as the reviewer.** The validator accepts `same_session` reviews but never counts them as independent (a warning; an error under `--strict`). The demo's reviews are same-session.
4. **Heuristic gates are heuristics.** `smooth`, `ghost` and `audio` (motion QA) and `cuts` (media QA) only warn and never prove anything. `flash` can fail a file, but it is a proxy for the three-flashes rule (large mean-luma swings in one second), not a WCAG conformance test.
5. **Declared stillness.** A mid-scene hold cannot be declared: only a "rest" of at most 1.2 s with no scheduled motion, or an end-of-scene hold. A scene that must stay still longer than that needs a moving visual or a shorter scene.
6. **Preview** timing is estimated from the text and unfinished assets are placeholders; a preview is not a QA verdict.
7. **Untested asset kinds:** images with transparency, focal-point cropping, extracted video frame sequences (`kind: "video"`), music beds.
8. **Render time.** Capture speed is recorded in every trace (ms/frame) and printed in the production report. Frames are screenshots of a real browser, so 1080p is slower than the demo's 640×360; read the number from your first real render before choosing 60 fps.
9. **Platforms.** Linux x86-64 only. macOS and Windows are untested. Rendering is byte-reproducible on identical Chromium and ffmpeg versions with the same worker count (default 2); another worker count, Chromium or ffmpeg can differ at text-edge pixels.
10. **No lock file.** The registry was unreachable. `package.json` has exact pins; run `npm install` once and commit the lock file.
11. **Creative claims are hypotheses.** Nothing here claims a technique raises retention or revenue; stage 07 exists to test that with the channel's own data.

## 5. How to turn UNTESTED into TESTED on your own machine
```bash
export ELEVENLABS_API_KEY=...                       # never printed or logged
python3 tools/new_project.py --idea "elevenlabs check" --slug el-check --purpose test_clip
# write a tiny scenes.json (or copy examples/smoke), then:
python3 tools/ledger.py --project videos/el-check approve --service elevenlabs --ceiling 600 --unit chars
python3 tools/voice.py --project videos/el-check --stack elevenlabs --voice-id <YOUR_VOICE_ID> --sample "One short sentence to hear the voice."
PAID_FAULT=after_submit python3 tools/voice.py --project videos/el-check --stack elevenlabs --voice-id <YOUR_VOICE_ID>   # crashes on purpose after the provider accepted (exit 99)
python3 tools/voice.py --project videos/el-check --stack elevenlabs --voice-id <YOUR_VOICE_ID>                          # must fetch from the provider's history and book no second request
python3 tools/ledger.py --project videos/el-check status                                                              # one submission per item
```
For Higgsfield, run one image in Claude Code through stage 02 with a 2-credit ceiling and check `ledger.py status` against the provider's own transaction list before approving more. Record the outcome in `library/lessons.md` and change the row above to TESTED only when it is.

## 6. Update from the first real production run (star-birth-to-black-hole-20261031, 31 Oct 2026, cloud session)
| integration | status now | evidence (this run) |
|---|---|---|
| Higgsfield image generation + **download** | **TESTED** | 6 × nano_banana_2 2k jobs → `ledger intent→submitted→done`; CloudFront result URLs downloaded with curl (HTTP 200) in this environment; provider transactions show 6 × 2 credits |
| Higgsfield voice (`text2speech_v2`, variant `elevenlabs`, preset "Knox") | **TESTED** | 42 takes/lines generated, downloaded, registered with `voice.py --stack file`; transactions show one charge per job; HTTP 429 refusals at submission created no job and no charge. Rate limit observed: batches of > 3 requests are partly refused (429) |
| Whisper alignment | **IMPLEMENTED + TESTED** (`tools/align.py --engine whisper` or `ALIGN_ENGINE=whisper`) | faster-whisper small.en word timestamps mapped onto the script with difflib; 1046/1058 words matched on the Knox narration; tests: `test_whisper_engine_fails_closed_without_speech_or_package`, `test_whisper_engine_aligns_real_speech_to_the_script`, `test_auto_alignment_never_selects_whisper_implicitly`. `auto` still never picks it implicitly |
| ElevenLabs direct API | UNTESTED (no key in this environment) | — |
