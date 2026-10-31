# Production report - demo

Idea: Smoke test: one frame, two shapes  ·  purpose: **smoke**  ·  made 2026-10-30T10:38:27

> This is a **smoke**, not a production video (a production video is at least 5:00 with its Shorts).

## Gate verdicts

| target | file | media QA | motion QA | length | size |
|---|---|---|---|---|---|
| long | out/full-video.mp4 | PASSED | PASSED | 12.7 s | 640x360 |
| S01 | out/short-01.mp4 | PASSED | PASSED | 14.167 s | 360x640 |

A verdict is the gate's own result on the delivered file. WARN items are heuristics and are listed under "A person still has to look at". PASSED never means the video is good, only that none of these checks found a defect.

## Transitions

- long s01>s02: **truthful_morph**
- long s03>s04: **dissolve**
- S01 s01>s02: **truthful_morph**

## Render

- long: 381 frames at 30 fps, 33.6 ms/frame with 2 worker(s) = 12.8 s of capture on this machine; a 60 fps render would take about 0.4 min
- S01: 425 frames at 30 fps, 35.2 ms/frame with 2 worker(s) = 15 s of capture on this machine; a 60 fps render would take about 0.5 min

## Voice and alignment

- voice: flite / slt - robotic; no emotion; for pipeline tests, drafts and the free path
- alignment: dtw_reference, coverage 1.0, median confidence 0.936; dtw_reference: reference voice flite/slt; median cost per frame 2.50

## Spend

- no paid service was approved or used (free path)

## A person still has to look at

- nothing flagged by the gates; still play the video once before publishing

## Notes from the run

- voice: ElevenLabs unavailable (no ELEVENLABS_API_KEY); FALLBACK to the free local voice flite (robotic, for drafts and tests)

## Reproduce

Engine 3.0.0-dom (browser, Chromium 153.0.8010.12); `python tools/pipeline.py run --project /home/claude/youtube-system/videos/demo` reproduces these files byte for byte on the same versions and worker count (the render is reproducible).
