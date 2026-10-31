---
description: Stage 06 - titles, thumbnails, description, chapters, Short copy, disclosure notes, credits and the production report.
argument-hint: [slug]
---
STAGE 06 - PACKAGE AND REVIEW. Follow CLAUDE.md §2 (H5, H6, H8), §3 (claims discipline). Video folder: `videos/<slug>/`. No paid calls.
RESUME: regenerate only files whose inputs changed.

1. `youtube.md`
   - 5 title options, each ≤ 60 characters, subject first, a real curiosity gap, nothing the video does not deliver.
   - 2–3 thumbnail concepts, written so they can run as a Test & Compare set if the channel is eligible (verify in Studio; YouTube judges variants by watch time).
   - Description: the hook and the main keyword in the first two lines; chapters; sources; credits; an AI-disclosure line if `disclosure.md` recommends one.
   - Chapter timestamps taken from the real render (`render/plan-long.json` scene windows): the first at 0:00, at least 3, each at least 10 s. Check them against the probed duration. (A `test_clip` has no chapters: write none.)
   - A pinned-comment question tied to the payoff; an end-screen plan; ad-break suggestions only if the video is long enough for mid-roll and only at natural scene ends (check current eligibility rules); a minimal tag list.
2. `shorts.md`: per Short a title (≤ 40 characters), a one-line description with the long video's link placeholder, a first comment, and the related-video link if the feature is available to the channel (verify). Give a release order with its reason, labelled as a hypothesis to test against channel data.
3. `disclosure.md`: for each asset class (generated images, synthetic voice, retrieved media, code graphics) state whether it shows realistic people, places or events, or a voice a viewer could take for a real person; classify against YouTube's altered/synthetic-content rule (disclosure is required for realistic content a viewer could mistake for real; clearly unrealistic or animated content and production help such as scripts or captions are exempt); recommend yes, no or unsure with the reason. The creator decides.
4. `credits.md`, final: sources, licenses and attributions, AI tools and models used, the ledger totals versus the approved ceiling for each service (`python3 tools/ledger.py --project videos/<slug> status`).
5. `production-report.md`: `python3 tools/report.py --project videos/<slug>` writes `review/production-report.md` from the run's own files (gate verdicts per file, transitions and downgrades, voice and alignment quality, spend per service, render timing, what a person still has to look at). Copy it next to your decisions log, deviations from the plan, waivers, known limitations and what to change next time; do not soften its verdicts.
6. LIBRARY. Copy `style-bible.md` and the tokens to `library/style-bibles/<slug>.md`; move reusable assets to `library/assets/` with their licenses; append lessons to `library/lessons.md` (label each as observed or hypothesis); write any calibrated QA thresholds to `library/thresholds.json`.
7. MEASUREMENT PLAN in `production-report.md`: what to read in YouTube Analytics after publishing (audience retention with its intro, spikes and dips; for each Short viewed vs swiped away and engaged views) and what to compare against (this channel's earlier uploads). Do not claim any outcome.
8. Set stage 06 to `done`; print the final report from `/make` step 6.

EXIT CHECKS: all files exist · chapter timestamps validated against the probed duration · the report was generated after the last render and its verdicts match the QA files · `credits.md` totals match the ledger.
