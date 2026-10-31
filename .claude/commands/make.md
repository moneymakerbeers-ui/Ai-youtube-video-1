---
description: Produce one long-form video plus 4-5 standalone Shorts from a single VIDEO_IDEA, or resume the active video
argument-hint: <VIDEO_IDEA> [KEY=value ...]  |  resume
---
Run the Universal YouTube Production System defined in CLAUDE.md (v3.1, locally hardened). Tools do the deterministic work (`tools/*.py`, `engine/`, `schema/`); you do the judgement work: research, story, scenes, graphics code, style, packaging text. Never do by hand what a tool does.

INPUT: $ARGUMENTS

1. PARSE
   - `resume` → go to RESUME below.
   - Empty → stop and tell the creator to type `/make <your idea>`.
   - Otherwise the text before the first `KEY=value` token is VIDEO_IDEA (any language or transliteration; the video language is LANGUAGE, default en-US). Never ask clarifying questions about the idea: take the most plausible reading and note it in one line.
   - `KEY=value` overrides CLAUDE.md §9. Keys: LANGUAGE, TARGET_DURATION (minutes, e.g. 6-9), AUDIENCE, CREATIVE_STYLE, VOICE_PROFILE, VOICE_STACK, BUDGET_MODE, MAX_PAID_SPEND (Higgsfield credits; above 20 counts as the creator raising the ceiling), OUTPUT_RESOLUTION, FPS, SHORTS_TARGET, RESEARCH_DEPTH, PURPOSE (`production` or `test_clip`).
   - If the creator asked for a short test video (for example "make a 1 minute test about X"), use PURPOSE=test_clip with TARGET_DURATION around 1 and one Short; the report labels it a test, never a production video.

2. SET UP (a new idea always starts a new video; only `resume` continues an old one)
   - slug = kebab-case of the first words of the English reading of the idea (at most 40 characters) + `-YYYYMMDD` (append `-2`, `-3` if the folder exists).
   - `python3 tools/new_project.py --idea "<idea>" --slug <slug> [--purpose test_clip] [--duration-min a,b] [--max-higgsfield-credits N] [--language L]` creates `videos/<slug>/` (config, state, neutral style tokens, folders). Write `input.md` (raw idea, one-line interpretation, overrides) and put the slug in `videos/.active`.

3. EXECUTE, in order, never skipping a stage and never starting one whose predecessor is not `done`:
   `00-preflight` → `01-research-script` → `02-assets` (free work, then ONE combined question: creative preview + per-service spend) → `03-voice` → `04-motion` → `05-render-shorts` (the pipeline) → `06-package-review`
   For each stage read `.claude/commands/<stage>.md`, follow it, check its EXIT CHECKS, run `npx tsx schema/validate.ts project videos/<slug>` before and after stages 01-06, update `state.json`. In a stage file `$ARGUMENTS` means the slug in `videos/.active` and the YAML header is metadata. Heavy stages (01, 04, 05) may run in a subagent when one is available; give it only paths (`CLAUDE.md`, `videos/<slug>/state.json`, the stage file).
   Stages 03-05 are one command once the inputs exist: `python3 tools/pipeline.py run --project videos/<slug> --auto-downgrade` (voice → assemble → align → Short audio → plans → lint → mix → render → captions → plan-aware allow-lists → media QA → motion QA → report, for the long video and every validated Short). It refuses (exit 5) until the creative preview is approved, and it never makes a paid call except through the ledger-gated voice adapter.

4. RESUME (`/make resume`)
   - Read `videos/.active` and `state.json`; tell the creator in one line where the video stands.
   - `python3 tools/ledger.py --project videos/<slug> status`. If it lists pending paid requests, handle each BEFORE anything else (never submit a paid job again to "see if it works"):
     - `submitted` (has a job id) → query the provider with that id (Higgsfield: `show_generations` / `jobs_wait`; ElevenLabs: history); when the result exists download it and `ledger.py done --key K --file …`; when it failed `ledger.py failed --key K`.
     - `intent` (no job id: the process died around the request, it may already have been charged) → look in the provider's history for a matching item (prompt/text, time). Found: `ledger.py resolve --key K --job-id J`, then treat as submitted. Not found: tell the creator, and only after they have looked at the provider's dashboard `ledger.py resolve --key K --abandon`.
   - `python3 tools/pipeline.py status --project videos/<slug>` shows which steps are done and which are stale; continue at the first unfinished stage. A finished step with unchanged inputs is skipped, so resuming is cheap and repeats nothing.

5. RULES FOR THIS RUN
   - Ask the creator only at the combined preview + spend question (stage 02), and for a BLOCKED item that needs a decision or credentials. Everything else: decide, log it in `production-report.md`, continue. Unanswered question: finish all free work, mark paid steps BLOCKED, stop.
   - A service you have not been approved to spend on is never called. Each service has its own ceiling in its own unit (credits, characters, dollars).
   - A failing gate is reported as FAILED, a gate that could not run as BLOCKED, with the exact cause. At most 2 fix cycles per failing item; at most 1 retry per paid asset. Never edit a threshold, a plan allowance or a report to make a file pass.
   - Chat output: one status line when a stage starts and one when it ends. No recaps, no file dumps.

6. FINISH
   `python3 tools/report.py --project videos/<slug>` (the pipeline already did) and print the final report (CLAUDE.md §6.6, at most 25 lines): the files with their gate verdicts, spend per service vs ceiling, key decisions, blocked items, and *what a person still has to look at*. Deliverables: `out/full-video.mp4`, `out/short-01.mp4` ..., `out/captions.srt`, thumbnails, `youtube.md`, `review/production-report.md`.
