# Production report - star-life-george-20261106

Idea: Star life cycle re-edit (video 7): from dust to black hole, George narration  ·  purpose: **production**  ·  made 2026-11-06T18:49:30

## Gate verdicts

| target | file | media QA | motion QA | length | size |
|---|---|---|---|---|---|
| S05 | out/short-05.mp4 | PASSED | PASSED | 48.4 s | 1080x1920 |

A verdict is the gate's own result on the delivered file. WARN items are heuristics and are listed under "A person still has to look at". PASSED never means the video is good, only that none of these checks found a defect.

## Transitions

- S05 r4>x1: **dissolve** (downgraded from match_movement: downgraded from match_movement by the motion gate: motion.r4>x1.exposure FAILED (match_movement flashes: luma excursion 9.8 levels, colour excursion 4.6, largest frame step 7.5 levels (flash risk)))

## Render

- S05: 1452 frames at 30 fps, 82.6 ms/frame with 4 worker(s) = 120 s of capture on this machine; a 60 fps render would take about 4.0 min

## Voice and alignment

- voice: file / externally supplied - as supplied
- alignment: whisper, coverage 1.0, median confidence 0.995; whisper (small.en, faster-whisper word timestamps) mapped onto the script: 600/605 script words matched a recognised word (99.2%); the rest are interpolated between matched neighbours (confidence 0.3); 11 words have confidence < 0.35: listen to them before trusting their timing

## Spend

- no paid service was approved or used (free path)

## A person still has to look at

- nothing flagged by the gates; still play the video once before publishing

## Reproduce

Engine 3.0.0-dom (browser, Chromium 153.0.8010.12); `python tools/pipeline.py run --project /home/user/Ai-youtube-video-1/videos/star-life-george-20261106` reproduces these files byte for byte on the same versions and worker count (the render is reproducible).
