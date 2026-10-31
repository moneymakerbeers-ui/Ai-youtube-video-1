# Lessons (appended by stages 04, 06 and 07; label each line `observed` or `hypothesis`)

Nothing recorded yet.

## 2026-10-31 · star-birth-to-black-hole
- observed: Higgsfield "Knox" (text2speech_v2 / elevenlabs) speaks ~112 wpm; a 1,058-word script ran 9:06. Plan ~115 wpm for this voice, or time-stretch (rubberband ×1.18 kept whisper transcription word-perfect).
- observed: text2speech_v2 batches of more than 3 requests get HTTP 429 on some items; submit in groups of 3. 429 = no job, no charge (verified in transactions) but the ledger still counts it as an attempt.
- observed: Higgsfield voice is billed in 0.15-credit steps (~0.0036 cr/char), not the 0.0031 implied by one long preview: book actuals from `transactions`, not estimates.
- observed: nano_banana_2 2k returns 2752×1536 (not exactly 16:9): crop to 16:9 before use or a 4 px band shows at scale 1.0.
- observed: on-screen text scales with the camera; push-ins > 1.2× carry corner tags off-frame. Keep tags near the centre or the push small; labels at depth 1.
- observed: landscape captions occupy ~0.82–0.93 of the height; keep labels above 0.78 (portrait above ~0.7).
- hypothesis: real telescope images (CC BY 4.0 / NASA) + a few labelled AI illustrations is the best quality-per-credit mix for astronomy topics.
- observed: 1080p render was 2 fps with 4 pages in ONE Chromium (single GPU/raster process pegged one core). One browser per worker → ~4 fps; JPEG q95 frame hand-off (RENDER_FRAME_FORMAT=jpeg) → ~12 fps. PSNR vs the PNG path 45 dB, SSIM 0.98 (visually identical after H.264).
