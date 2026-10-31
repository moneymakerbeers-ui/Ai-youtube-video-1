# Quality gates (read in stages 01, 04, 05)

Principles: check the **whole timeline** by machine, then look with judgement where risk is highest. Gates compare what a file contains with what the plan declares, so only the unplanned fails. They **fail closed**: a gate passes only with evidence, and a gate that cannot run or be trusted is BLOCKED, never green. Thresholds are starting points (the code defaults are in `tools/qa_media.py` and `tools/qa_motion.py`; a project may override them with `--thresholds`), calibrated on real renders. Never loosen a threshold or a plan allowance to make one file pass without logging why in `library/lessons.md`. At most 2 fix cycles per failing item.

## 1. Where each check runs
| when | check | tool |
|---|---|---|
| stage 01 | schema and cross-file validation (claims, Short back-references, asset ids, voice caps, anchors, timing); script lint; **evidence review** (snapshots opened, quotes found, numbers traced); **independent reviews** of claims and Shorts | `schema/validate.ts`, `tools/lint_script.py`, `tools/check_evidence.py`, `review/*.json` |
| stage 02 | palette contrast; licence evidence; creative preview | `tools/contrast.py`, `tools/preview.py` |
| stage 03 | takes registered; alignment trustworthy; each Short's own audio aligned | `tools/voice.py`, `tools/align.py`, `tools/short_audio.py` |
| stage 04 | engine maths; plan warnings (anchors beyond a clamp, long unscheduled stillness); draft run through the real gates | `tests/engine`, `tools/make_plan.py`, `tools/make_allow.py --check`, `tools/pipeline.py` |
| stage 05 | final media QA and motion QA on every file; thumbnails; report | `tools/qa_media.py`, `tools/qa_motion.py`, `tools/thumbnail.py`, `tools/report.py` |

Exit codes of every QA tool: `0` PASSED · `1` FAILED (something unplanned or wrong was measured) · `3` BLOCKED (a measurement could not run or be trusted) · `2` usage. Overall = FAILED if any check fails, else BLOCKED if any is blocked, else PASSED.

## 2. Fail-closed rules (what v2 got wrong and v3 enforces)
- Every subprocess exit code is checked and its log scanned for `[error]`, `[fatal]`, "No such filter", "Invalid argument". v2 read ffmpeg output without looking at its exit code, so a broken filter graph produced empty logs and every gate passed. `QA_FAULT=bad_filter` reproduces that and must produce FAILED/BLOCKED (regression test A1).
- Every measurement stream is checked for **coverage**: samples against frames expected, last timestamp against the duration (`coverage.minFraction` 0.985).
- Before a file is judged the detectors run on 3 s of synthetic media with known black, static and silent spans and must find exactly those; otherwise the detector gates are BLOCKED (`QA_FAULT=selfcheck_fail`).
- **No blanket allowances** (`tools/make_allow.py`). Black is tolerated only in the declared opening fade and ending fade/hold; stillness only in a declared hold or a "rest" (a gap in which the plan schedules no entrance, exit, camera move or transition, at most 1.2 s); silence only where the assembly recorded it (declared pauses, take joins, lead and tail). Each tolerated event must lie inside its window, and a declared black, hold or silence that is *missing* also fails. An accidental black tail, a frozen frame while the plan schedules motion, an unplanned silent narration span all FAIL.

## 3. Media QA (`tools/qa_media.py`)
| id | checks | default | severity |
|---|---|---|---|
| selfcheck | the detectors find known events on synthetic media | exact | blocked |
| decode | full decode, zero diagnostics, frame count equals the plan | 0 errors | fail |
| probe.size / codec / color / fps | pixel size (from the plan), H.264 + yuv420p, BT.709 tv-range tags, constant frame rate equal to the plan | exact | fail |
| probe.duration, probe.audio, av.duration | duration equals the plan; AAC 44.1/48 kHz present; audio and video lengths agree | ≤ 0.10 s | fail |
| short.length | a Short is ≤ 180 s | 180 s | fail |
| black | black outside declared windows, or a declared black that is not there | 0.03 s, pix 0.10 | fail |
| freeze, freeze.source | stillness measured exactly at the renderer (scene-graph hashes, zero tolerance) **and** in the delivered file (largest change of any block of the pooled picture, which sees small movers that a whole-frame mean misses); the file may be still only where the scene graph is | 0.4 s | fail |
| freeze.shimmer | the file changes where the scene graph is still | – | warn |
| silence | silence not recorded by the assembly (dead air) | 0.7 s at −45 dB | fail |
| narration | silent spans where the alignment says words are spoken | 0.5 s, ≥ 3 words | fail |
| loudness | integrated LUFS, true peak; an engineering target, not a YouTube requirement: calibrate by ear and against this channel's uploads | −14 ± 1.5 LUFS, ≤ −1 dBTP | fail |
| sync | the audio in the file against the master mix | ±0.05 s | fail |
| flash | large mean-luma swings in one second: a heuristic for the 3-flashes rule, not a WCAG conformance test | < 6 swings | fail |
| cuts | scene-change jumps the plan does not explain | score 0.35 | warn |
| sheets | contact sheets for the eyes (`qa/sheets/<target>/`) | n/a | info |

## 4. Motion QA (`tools/qa_motion.py`): inside every planned transition window of the delivered file
Mechanical (`fail`): `boundary` (no spike at the window edges), `exposure` (frame step, pulse against a rolling median, bulge beyond the two ends, colour excursion), `stall` (the renderer drew motion the file does not show, or an operator stuck mid-move; the settled tail of an ease is not a stall), `pop` (an isolated interior frame that departs from its neighbours), `anchor` (landing at both ends, lock, straight-line path, monotone travel, scale jump, aspect). Heuristic (`warn`): `smooth` (local jerk), `ghost` (a double image where a match is promised), `audio` (an abrupt step or click at the window edges; steps the narration itself makes are exempt). Also writes `render/previews/<target>/tr-<from>-<to>.mp4` (window ±0.5 s with audio) and `-strip.png` (10 frames across it). The instruments first run on synthetic good, pop, flash and stall transitions and must classify all four (`--selfcheck`; otherwise BLOCKED). Heuristics are not proof; a pass is not proof of beauty.

## 5. Evidence and editorial review (on top of schema validity)
A schema proves a field is filled in; it cannot prove it is true. `tools/check_evidence.py` opens the files: `snapshot_missing`, `snapshot_changed` (sha256), `quote_not_found` (after whitespace, quote and dash normalisation), `quote_too_short` (a "direct" quote under 6 words), `number_untraceable` (a number the narration speaks that appears in none of the claim's text, wording or quotes), `claim_unused`, `scene_number_no_claim`, `source_not_independent`. It lists separately what only a person can judge: `model_processed` (a quote checked only against text a model returned) and `interpretation` (whether the passage really supports the claim). Then an independent reviewer writes `review/evidence-review.json` and `review/shorts-review.json` (verdict, reason, quoted problems); `same_session` is allowed but never counts as independent and the validator warns (`--strict` fails). Mechanical findings, subjective judgements and human-needed items are kept apart and every finding says what to do next.

## 6. Creative preview gate
`tools/preview.py make` writes `review/preview/` (hero and technical stills in 16:9 and 9:16, the first complex transition as a clip in both shapes, a voice sample, a contact sheet). The creator approves once (`preview.py approve`), together with the per-service spend; `pipeline.py` refuses (exit 5) when the approval does not match the current creative fingerprint. Timing in a preview is estimated and unfinished assets are labelled placeholders: a preview is not a QA verdict.

## 7. Deterministic layout checks (engine and schema, from scene data)
Each non-backdrop entity box inside the frame; portrait: key content inside the margins (defaults top 8 %, bottom 18 %, left 6 %, right 12 %; engineering margins, not platform specs); minimum text height 48 px on a 1080 px short side; no overlapping text boxes; label colour against the style tokens passes `tools/contrast.py`; every Short scene has an explicit portrait layout; anchors inside the frame in both layouts.

## 8. Visual review (token-budgeted, about 40 images per pass)
Long video: contact sheets plus the transition strips (ranked: complex transitions first). Shorts: their sheets and strips, always the opening frames at 0, 0.5 and 1.0 s. Look for: text clipped or inside UI zones; low contrast; generated-image artefacts (hands, faces, garbled marks, stray text); a style that drifts between scenes; a palette jump; banding; a label that does not match the narration; a transition that breaks the grammar. Write what you saw, briefly, in `qa/visual-review.md`.

## 9. Final playback verification (stage 05)
`ffprobe` stream facts (recorded with sha256 in the report); full decode with zero errors (media QA `decode`); audio and video durations within 0.1 s; first and last frame viewed; chapter timestamps in `youtube.md` checked against the probed duration.

## 10. Human checks the system cannot do (always listed in the report)
1. Listen to the first 60 seconds: does the voice sound right and honest? (A synthetic free voice never will: it is for drafts and tests.)
2. Watch each Short on a real phone: opening 3 seconds, caption readability, nothing hidden behind platform controls.
3. Judge the transitions by eye at full speed.
4. Spot-check three claims against their sources, and every item `check_evidence.py` lists as human-needed.
5. Answer YouTube's altered/synthetic-content question using `disclosure.md`; confirm the thumbnail is honest.

## 11. Status vocabulary
Per file the gates' own verdict: **PASSED** (no check found a defect; heuristic warnings may remain and are listed), **FAILED** (a check measured a defect: cause and time range given), **BLOCKED** (a measurement could not run or be trusted), **NOT RUN**. A skipped gate or a waiver is never PASSED. Per integration, `docs/STATUS.md`: **TESTED** (a call in a test run succeeded), **UNTESTED**, **BLOCKED**. The report lists verdicts per file plus the human checks.
