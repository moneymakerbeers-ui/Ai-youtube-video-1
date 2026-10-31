# v3 report: what changed from v2, and how it was tested

Date of the build and test run: 30 Oct 2026. Honest status of every integration: `docs/STATUS.md`. This file is the engineering account.

## 1. Real corrections to v2
| # | what v2 got wrong | what v3 does | proof |
|---|---|---|---|
| 1 | **No render engine.** v2 described a Remotion engine that was never installed or run; its `package.json` had no runtime dependencies and pinned a zod version nothing exercised. (The review finding "tsconfig.json not present" was a packaging artifact: the file existed, my concatenated review bundle left it out.) | A real engine: the scene graph is drawn in Chromium through Playwright from a plan JSON, bundled with esbuild, frames piped to ffmpeg (H.264, BT.709, AAC). `tsconfig.json`, exact pins, one install and one render command, byte-identical re-renders (same versions and worker count). Remotion is not used: it could not be installed in the build sandbox, and the plan JSON is the interface if you want to port. | every pipeline test, `test_d…determinism`, `test_d…colours_survive_encoding`, `npm run typecheck` |
| 2 | **QA passed on a broken instrument.** `qa_media.py` read ffmpeg's output without checking its exit code, so a bad filter graph gave empty logs and every gate passed. | Fail closed: every subprocess exit code and log is checked, every measurement must cover the file, and the detectors first find known events on synthetic media or the gates are BLOCKED. Exact cause and time range in every FAILED/BLOCKED. | A1: `test_a1_broken_instrument_is_never_a_pass`, `…ffmpeg_missing_is_blocked…`, `…corrupt_file…` |
| 3 | **Blanket allowances.** `make_allow.py` tolerated black at the end of every file, silence at both ends, a half-pause margin at every boundary and a whole-scene freeze whenever the camera was empty, so real defects hid inside them. | Allowances come only from the plan, each with its own time window; the event must lie inside it, and a declared black/hold/silence that is missing also fails. No declared fade means no tolerated black. | A2, A3, `test_d…allow_lists…` |
| 4 | **No motion QA.** Transitions were checked with one luma number. | `qa_motion.py` on the delivered frames inside every window: boundary, exposure, stall (renderer-aware), pop, anchor landing/lock/path/scale/aspect (mechanical); jerk, ghosting, abrupt audio (heuristic); short preview clips and strips to look at; instrument self-check. Auto-downgrade of a failing complex transition, recorded. | A6, `test_c_operator_matrix` (16 real transitions), `test_b…downgrade…` |
| 5 | **Evidence by boolean.** A claim was "verified" by a status field and a source label. | Evidence pointers (snapshot, hash, exact quote, how it supports); `check_evidence.py` opens the files; independent evidence and Shorts reviews as data; model-processed text never counts as proof; numbers the narration speaks must trace to a claim. Mechanical, subjective and human-needed findings kept apart. | A4 (`test_a4_*`) |
| 6 | **Timing from audio was a promise.** No aligner existed, and a Short reused the long video's timestamps although it has its own lines. | `align.py` (DTW against a same-voice reference, ElevenLabs forced alignment adapter) with coverage/quality numbers; a Short is assembled from its own scene windows and lines and aligned again on that audio; stale Short audio is refused. | A5 |
| 7 | **One credits ceiling, no resume safety.** | Per-service approval and ceilings in their own units; a ledger `intent → submitted(job) → done/failed`; a resume queries the provider for a submitted job and never resubmits, and refuses to guess after an interrupted intent; free fallback with a visible FALLBACK note. | A8, A9 |
| 8 | **No look-before-you-pay.** | Creative preview gate: hero and technical shot in both shapes, a transition clip, a voice sample, approved once together with the spend; the pipeline refuses without a matching approval. | `test_b…preview…` |
| 9 | **`/make` was prose.** | `/make <VIDEO_IDEA>` and `/make resume` drive real tools (`new_project`, `doctor`, `ledger`, `preview`, `pipeline`, `thumbnail`, `report`) with documented exit codes. | `test_b…scaffold…`, A7 |
| 10 | **Status by assertion.** | `doctor.py` reports AVAILABLE only for commands that just ran; live services are UNTESTED until a call succeeds; `report.py` is built from the run's own files; `STATUS.md` states what was and was not tested. | A9, `test_b…report…` |
| 11 | Found late, while building the demo: **the renderer's frame queue was first-come-first-served**, so a page's raster history (and with it text-edge pixels, up to 44 luma levels in 60-120 of 425 frames of the demo Short) changed from run to run. Fixed with a fixed frame-to-page assignment; 3 of 3 re-renders are now byte-identical and the determinism test covers the Short as well as the long video. Also:  `align --engine auto` would pick an unimplemented whisper engine when faster-whisper was installed; `config.fps` was never read; an unused OpenCV check was reported by the doctor; the pipeline `steps` listing and docstring were out of date. | fixed, and covered | `test_e_regressions_and_assets.py` |

## 2. Architecture in one picture
```
scenes.json (one semantic scene graph; landscape + portrait layouts; voice, transitions, claim ids)
 ├─ voice.py ─► takes ─► assemble ─► align ─► alignment.json         (Shorts: short_audio.py → own audio + own alignment)
 ├─ make_plan.py ─► render/plan-<target>.json  (timing truth: scene windows, transitions + anchors, captions, silences, holds)
 ├─ engine/render.ts: plan ─► Chromium frames ─► ffmpeg ─► out/full-video.mp4 · out/short-NN.mp4   (+ trace: state hashes, anchors, source motion)
 ├─ mix.py (two-pass loudnorm) · captions
 ├─ make_allow.py (what the plan authorises) ─► qa_media.py ─► qa_motion.py ─► downgrade.py ─► re-plan/render/QA (≤ 2 rounds)
 └─ report.py ─► review/production-report.md        thumbnail.py ─► out/thumbnail-N.jpg
ledger.py gates every paid call · preview.py gates the whole pipeline until the creator approves look + voice + structure
```

## 3. The nine acceptance tests
| # | requirement | test (file `tests/`) | what it does |
|---|---|---|---|
| 1 | a bad ffmpeg diagnostic makes QA fail | `test_a1_a2_a3_qa_fails.py::test_a1_broken_instrument_is_never_a_pass` (+ 2 more) | injects a broken filter graph, a missing ffmpeg and a corrupt file; the verdict is FAILED or BLOCKED with the cause, never PASSED; a clean baseline still passes |
| 2 | an accidental black tail fails | `…::test_a2_black_tail_on_a_file_with_declared_fade_fails`, `…without_declared_fade…`, `…declared_fade_that_is_missing…` | appends black to a real render |
| 3 | an unexpected silent narration span fails unless authorised | `…::test_a3_unexpected_silent_narration_span_fails`, `…declared_pause_is_authorised…` | mutes a span where words are aligned; an authorised pause passes, an extra one does not |
| 4 | a missing asset or claim reference fails validation | `test_a4_a5_validation_and_shorts.py::test_a4_*` (7 tests) | missing claim, asset, scene reference; evidence pointing at a missing or altered snapshot; a spoken number not in the source; model-processed text never reported as proof |
| 5 | a Short with new voice lines has its own aligned audio | `…::test_a5_short_has_its_own_audio_and_alignment`, `…stale_short_audio_is_refused…` | the Short's `narration.wav`, alignment and plan differ from the long video's |
| 6 | real transition frames are inspected for pops and geometric continuity | `test_a6_a7_transitions_and_two_ratios.py::test_a6_*` (8 tests), `test_c_operator_matrix.py` | decodes the real frames of every transition; injected pop, flash, stall and anchor defects are caught; 16 real transitions across 8 operators pass; the instrument's self-check can block |
| 7 | the CLI produces two aspect-ratio videos from shared scene data | `…::test_a7_cli_produced_both_videos_from_the_same_scene_data`, `…both_files_play_through…`, `…pipeline_is_resumable…`; `test_c…the_same_scene_data_drives_both_shapes` | 16:9 and 9:16 files from one `scenes.json`, probed and fully decoded |
| 8 | a resume never repeats a paid generation | `test_a8_a9_paid_and_blocked.py::test_a8_*` (4 tests) | crash after the provider accepted → resume fetches from history, one request per item; crash before the request → refused, not blindly resent; a finished item is never paid again |
| 9 | a missing tool or quota gives an honest BLOCKED or a documented free fallback | `…::test_a9_*` (8 tests) | no key → exit 3, nothing booked; not approved / over the ceiling / wrong currency → exit 4; no key under `--stack auto` → flite with a FALLBACK note; missing ffmpeg and missing Chromium named; live services labelled UNTESTED |

Extra suites: auto-downgrade, preview gate, report, scaffold, thumbnails (`test_b`), operator matrix (`test_c`), allow-lists, determinism, colour fidelity (`test_d`), regressions and the raster-image path (`test_e`), 84 engine unit tests for the transition maths (`tests/engine/transitions.test.ts`).

## 4. Result of the full run
`npm test` (typecheck → schema self-test → engine unit tests → pytest), started from an empty `tests/.work`, `FRESH=1`, on the 2-CPU build sandbox, 30 Oct 2026 09:26–09:37 UTC: **EXIT CODE 0, every stage green.**

| stage | result |
|---|---|
| `tsc -p tsconfig.json` (typecheck) | no errors |
| `schema/validate.ts selftest` | `SELFTEST PASSED (30 rules proven)`: 38 `ok` lines (8 example files validate, 30 rules shown to bite, controls stay valid) |
| `tests/engine/transitions.test.ts` (node:test) | 84 tests, 84 pass, 0 fail, 0 skipped (0.29 s) |
| `pytest tests -q` | **72 passed** in 643 s (10 min 42 s) |
| whole `npm test` | 10 min 48 s wall clock |

Raw output (583 lines, unedited): `docs/test-evidence/npm-test.log`. Environment: see `INSTALL.md` §9. What this does not prove is in `docs/STATUS.md`: nothing here called ElevenLabs, Higgsfield or YouTube.

## 5. The demo (free, synthetic) in `demo/`
Command (from `INSTALL.md` §4, run twice from scratch): `python3 tools/pipeline.py run --project videos/demo --size 640x360 --auto-downgrade`, 57 s each, exit 0 both times. The two runs gave **identical SHA-256** for both MP4s (`demo/SHA256SUMS`).
| file | what | probe (ffprobe) | gates |
|---|---|---|---|
| `demo/full-video.mp4` | 16:9, 4 scenes, free flite voice | 640x360, H.264 High, yuv420p, BT.709 tv, 30 fps, AAC 48 kHz stereo, 12.7 s, fully decoded with no error | media QA PASSED (19 pass), motion QA PASSED |
| `demo/short-01.mp4` | 9:16 recomposed from the same `scenes.json`, own audio + alignment | 360x640, same codecs, 14.17 s, fully decoded | media QA PASSED, motion QA PASSED |
Content: narration, graphics synchronised to aligned words, one truthful morph (frame 16:9 to 9:16), a dissolve, two cuts, a deliberate hold. Inspected: transition strips `demo/previews/*/tr-*-strip.png` and contact sheets `demo/qa/sheets/`; I looked at them and the morph, labels and captions behave as planned. Not judged by a machine: voice (robotic by design), taste. Report: `demo/review/production-report.md`.

## 6. Decisions worth knowing
- **DOM + Chromium instead of Remotion.** The sandbox could not install Remotion; the engine uses only what was installable and testable (Playwright, esbuild, ffmpeg). Frame capture is screenshot-based, so render time is roughly proportional to frames × ms/frame (printed in every report).
- **30 fps by default.** `config.fps` or `--fps 60` for 60; the report shows what 60 would cost.
- **A free voice that sounds robotic, on purpose.** It lets every stage, test and demo run with no account; the paid or studio voices plug in through `voice.py` (`elevenlabs`, `file`).
- **Heuristics warn, mechanics fail.** A single moved threshold must never turn a red run green: thresholds are logged in `library/lessons.md` when changed.
- **Same-session reviews are allowed but never independent.** The validator warns (error under `--strict`) so a lazy self-review cannot pass as a second opinion.

## 7. Next steps that only real use can provide
Run the live checks in `docs/STATUS.md` §5 with real keys; make one real 6–9 minute video as the shakedown and calibrate `library/thresholds.json` from its false positives; replace the free voice with a natural one; install the lock file.
