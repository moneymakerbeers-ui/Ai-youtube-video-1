# Production report - star-life-george-20261106

Idea: Star life cycle re-edit (video 7): from dust to black hole, George narration  ·  purpose: **production**  ·  made 2026-11-06T19:26:41

## Gate verdicts

| target | file | media QA | motion QA | length | size |
|---|---|---|---|---|---|
| long | out/full-video.mp4 | PASSED | PASSED | 218.533 s | 1920x1080 |
| S01 | out/short-01.mp4 | PASSED | PASSED | 35.367 s | 1080x1920 |
| S02 | out/short-02.mp4 | PASSED | PASSED | 33.1 s | 1080x1920 |
| S03 | out/short-03.mp4 | PASSED | PASSED | 46.533 s | 1080x1920 |
| S04 | out/short-04.mp4 | PASSED | PASSED | 34.467 s | 1080x1920 |
| S05 | out/short-05.mp4 | PASSED | PASSED | 47.7 s | 1080x1920 |

A verdict is the gate's own result on the delivered file. WARN items are heuristics and are listed under "A person still has to look at". PASSED never means the video is good, only that none of these checks found a defect.

## Transitions

- long c3>p1: **nested_scale**
- long f2>b1: **match_movement**
- long b2>m1: **match_movement**
- long m4>o1: **match_movement**
- long k3>e1: **match_movement**
- long e2>e3: **dissolve** (downgraded from depth_through_object: downgraded from depth_through_object by the motion gate: motion.e2>e3.exposure FAILED (depth_through_object flashes: luma excursion 40.5 levels, colour excursion 50.3, largest frame step 39.0 levels (flash risk)))
- long r4>x1: **match_movement**
- long g3>z1: **match_movement**
- S01 c3>p1: **dissolve** (downgraded from nested_scale: downgraded from nested_scale by the motion gate: motion.c3>p1.exposure FAILED (nested_scale flashes: luma excursion 19.5 levels, colour excursion 22.0, largest frame step 5.4 levels (flash risk)))
- S03 k3>e1: **dissolve** (downgraded from match_movement: downgraded from match_movement by the motion gate: motion.k3>e1.exposure FAILED (match_movement flashes: luma excursion 0.7 levels, colour excursion 0.7, largest frame step 27.2 levels (flash risk) (+1 more failed check)))
- S05 r4>x1: **dissolve** (downgraded from match_movement: downgraded from match_movement by the motion gate: motion.r4>x1.exposure FAILED (match_movement flashes: luma excursion 9.8 levels, colour excursion 4.6, largest frame step 7.5 levels (flash risk)))

## Render

- long: 6556 frames at 30 fps, 83.7 ms/frame with 4 worker(s) = 549 s of capture on this machine; a 60 fps render would take about 18.3 min
- S01: 1061 frames at 30 fps, 83.5 ms/frame with 4 worker(s) = 88.6 s of capture on this machine; a 60 fps render would take about 3.0 min
- S02: 993 frames at 30 fps, 81.8 ms/frame with 4 worker(s) = 81.2 s of capture on this machine; a 60 fps render would take about 2.7 min
- S03: 1396 frames at 30 fps, 82.2 ms/frame with 4 worker(s) = 114.8 s of capture on this machine; a 60 fps render would take about 3.8 min
- S04: 1034 frames at 30 fps, 83.9 ms/frame with 4 worker(s) = 86.7 s of capture on this machine; a 60 fps render would take about 2.9 min
- S05: 1431 frames at 30 fps, 82.2 ms/frame with 4 worker(s) = 117.6 s of capture on this machine; a 60 fps render would take about 3.9 min

## Voice and alignment

- voice: file / externally supplied - as supplied
- alignment: whisper, coverage 1.0, median confidence 0.995; whisper (small.en, faster-whisper word timestamps) mapped onto the script: 600/605 script words matched a recognised word (99.2%); the rest are interpolated between matched neighbours (confidence 0.3); 11 words have confidence < 0.35: listen to them before trusting their timing

## Spend

- no paid service was approved or used (free path)

## A person still has to look at

- long: motion.f2>b1.smooth (heuristic warning) - a frame step is 10.3 levels above its neighbours' typical 12.3 (a jerk; smaller than a pop)
- long: motion.b2>m1.smooth (heuristic warning) - a frame step is 7.9 levels above its neighbours' typical 9.1 (a jerk; smaller than a pop)
- long: motion.m4>o1.smooth (heuristic warning) - a frame step is 13.0 levels above its neighbours' typical 13.9 (a jerk; smaller than a pop)

## Reproduce

Engine 3.0.0-dom (browser, Chromium 153.0.8010.12); `python tools/pipeline.py run --project videos/star-life-george-20261106` reproduces these files byte for byte on the same versions and worker count (the render is reproducible).
