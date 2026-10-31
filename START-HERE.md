# START HERE (3 steps)

## 1. Install once (needs Node 22+, Python 3.13 (recommended for the pinned requirements), ffmpeg)
```bash
unzip youtube-system-v3.1-fixed.zip && cd youtube-system
npm install
npx playwright install chromium
python3 -m pip install -r requirements.txt      # prefer a virtual environment; do not modify system Python
python3 tools/doctor.py                          # must not say MISSING for anything required
```

## 2. Open Claude Code in this folder
```bash
claude
```
Claude Code reads `CLAUDE.md` by itself. That file is the whole system prompt; you do not paste anything else.

## 3. Type ONE line
```
/make <your video idea, any language, even Finglish>
```
Example: `/make why the moon always shows the same face to Earth`

What happens: it researches with sources, writes the script, builds graphics in code, narrates (free voice unless you approve a paid one), renders the 16:9 video and the 9:16 Shorts, runs the quality checks and writes `videos/<slug>/review/production-report.md`.
It asks you ONE question per video: approve the look/voice preview and the spend per service (Higgsfield credits, ElevenLabs characters), or say "free only".

Files you get in `videos/<slug>/out/`: `full-video.mp4`, `short-01.mp4` ... `short-05.mp4`, `captions.srt`, thumbnails, `youtube.md` (title, description, chapters).

If it stops or you close the window: `claude` again, then `/make resume`. It never pays twice for the same generation.

Optional paid voice (ElevenLabs): set `ELEVENLABS_API_KEY`, and the system writes your chosen voice into the video's `config.json` (`voice.elevenlabs.voiceId`, `model`) once; you are not asked again and `/make` forwards it everywhere. Without a key or paid approval it uses the free robotic voice and says so. If ElevenLabs was approved but no voice ID was selected, the run stops rather than silently downgrading voice quality.

Optional: `/make <idea> FPS=60`, `/make <idea> MAX_PAID_SPEND=0`.

Honest status of Higgsfield / ElevenLabs / YouTube (what was and was not tested): `docs/STATUS.md`.
