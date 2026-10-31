---
description: Stage 00 - inventory tools with evidence, record prices, decide the voice stack, validate config. No creative work, no spending.
argument-hint: [slug]
---
STAGE 00 - PREFLIGHT. Follow CLAUDE.md. Video folder: `videos/<slug>/` (slug = `$ARGUMENTS`, else the contents of `videos/.active`).
RESUME: read `state.json`. If this stage is `done` and `config.json` is unchanged, say "already done" and stop.
NOTHING PAID: price previews are free; do not submit any generation job in this stage.

1. CONFIG. `new_project.py` wrote `config.json` with the defaults. Merge `channel.md` (if present) and the `KEY=value` overrides from `input.md` into it. Set `maxPaidSpend.higgsfieldCeilingRaisedByCreator=true` only if the creator gave MAX_PAID_SPEND above 20. Validate: `npx tsx schema/validate.ts config videos/<slug>/config.json` (if dependencies are missing: `npm install` once, then `npx playwright install chromium`, then retry).
2. INVENTORY. `python3 tools/doctor.py --project videos/<slug> --json videos/<slug>/tools.json` (add `--net` to also try the service hosts). It prints one line per item: AVAILABLE (a command just ran and produced the expected result), MISSING, UNTESTED (needs an account, key or network the check does not use), BLOCKED (checked and refused). Exit 3 means something required is MISSING: give the exact install command from its `howToFix` and stop as BLOCKED. Then add what only you can see, each as available / unavailable / unverified with evidence from this run:
   - Higgsfield MCP tools: list them, read `balance`, note the selected workspace.
   - ElevenLabs: an MCP server or `ELEVENLABS_API_KEY` (check presence only; never print or log it).
   - research: is web search and fetch available?
   - terms: the commercial-use terms of the ElevenLabs and Higgsfield plans (look up the current pages); record the finding with its URL, or `unverified`. The creator confirms what applies to their plan.
   UNTESTED is the honest state of a live service until a call in this run succeeded; never promote it by assumption.
3. PRICES (free previews). For every paid model stages 02 or 03 might use, record the credits for the exact parameters (model, quality, resolution, aspect) from the tool's price preview into `prices.json` with a timestamp. Unknown credit-to-dollar rate → `dollarsPerCredit: null`. A price you did not measure is `unknown`, never a guess.
4. VOICE STACK. Decide and record the expressiveness ceiling in `preflight.md`: (A) ElevenLabs with a key and an approval · (B) Higgsfield voice through the MCP tools, takes registered with `voice.py --stack file` · (C) `file`: takes the creator supplies · (D) `flite`, the free local voice (robotic; drafts, tests and the preview). The free voice is always available when `doctor.py` shows libflite, so the run is never blocked on a voice, only limited in quality (say so).
5. RENDER SPEED. fps is 30 unless the creator asked for 60 (`FPS=60`). The engine records ms/frame in every render trace and the report shows what 60 fps would cost, so no separate benchmark is needed; on the first long render read the number and tell the creator if the total looks long.
6. ENGINE HEALTH. `npm run typecheck` and `npm run selftest` must pass. (`npm test` runs the whole suite and takes a few minutes; run it when the engine or a tool was changed.)
7. WRITE `preflight.md` (table, at most 60 lines: item · status · evidence · fallback), `tools.json` (from the doctor), `prices.json`, and one line per quality limit this machine imposes (for example "no ElevenLabs key: narration uses the free local voice and will sound robotic"). Set stage 00 to `done` in `state.json`.

EXIT CHECKS: `config.json` validates · every preflight line has evidence · `state.ledger` shows zero spent · voice stack decided · the doctor reported no MISSING required item.
