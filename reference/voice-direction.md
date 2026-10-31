# Voice direction (read in stage 01 for scene voice, in stage 03 for production)

One narrator **identity** per video; the **performance** changes per scene. Calm is not monotone. Emotion comes from the material; serious material gets none that is manufactured.

## 1. Identity (fixed per video)
Choose by topic fit, not habit: register (warm, dry, intimate, authoritative), energy the subject can carry for 6–9 minutes, clarity for a general US audience, stamina across paragraphs. Record the reason in `audio/voice.md`. Not always a calm male voice. `channel.md` may fix a channel voice; otherwise pick per video. Never clone or imitate a real person without documented permission (H2). Fix voice ID, model and base settings for the whole video; take-to-take settings drift is a defect.

## 2. Performance fields (`scenes[].voice`, schema `VoiceDirection`)
| field | meaning |
|---|---|
| `intent` | what the line must do for the viewer (orient, reveal, soothe, warn, hand over a question) |
| `emotion` | one or two words from the vocabulary below; free text is allowed if it is a plain human description |
| `intensity` | 0 plain · 1 gentle colour · 2 clearly expressive · 3 peak (rare: at most 3 per long video, never in a Short opening unless the line earns it) |
| `pace` | slower / steady / faster, relative to the narrator's base pace |
| `emphasisWords`, `pauseBeforeMs`, `pauseAfterMs`, `deliveryNotes` | small, concrete, only where non-default |
| `pronunciation` | TTS-only respellings; never shown in captions |
| `takeId` | written by stage 03 |

Vocabulary (combine at most two): neutral-clear · warm-explanatory · curious · quiet-wonder · measured-concern · gentle-humour · matter-of-fact · reflective · tender · resolute · urgent (rare).
Defaults: `neutral-clear`, intensity 0. Raise intensity only at a reveal, a reversal, a payoff or a human stake, then settle. Plan the contour per section from `retention-map.md`: baseline 0–1, peaks where the facts peak. A long video with one emotion at one intensity throughout is a defect; so is constant high energy.

## 3. Sensitivity caps (CLAUDE.md H3)
Intensity cap: normal 3 · care 2 · high 1. On care/high material use neutral-clear, warm-explanatory, measured-concern, reflective, tender; no excitement, awe at suffering, irony, dramatic whispers, or comedic timing. Respect over effect.

## 4. Compile to the model (stage 03 steps 2-3)
`spoken_script.txt` and `scenes[].narration` stay clean. `tools/voice.py` applies only the per-scene pronunciation respellings and writes the exact text of each take to `audio/take-plan.json`; it does **not** compile bracketed audio tags or settings. This section is for takes you produce yourself (`--stack file`, for example with Higgsfield voice or another studio) and for choosing an ElevenLabs model and settings: always check the model's current documentation in this run; the table is the starting point.
| voice stack (from `tools.json`) | how direction is expressed |
|---|---|
| A: ElevenLabs v3/v4-class | bracketed audio tags at the start of the sentence they affect (1–2 per sentence at most; prefer voice-quality or emotion descriptions over sound-effect tags; tag support varies by voice, so audition); punctuation, ellipses and capitals for emphasis; no SSML break tags on these models, so pauses are punctuation inside a take and true silence between takes |
| B: ElevenLabs without tags (v2-class) | punctuation and sentence shape; the documented speed range (0.7–1.2); break tags only where the model supports them; stability and style settings are fixed per video, with a per-take change only if the audition proves a benefit |
| C: local TTS | punctuation only; say in `preflight.md` that expressiveness is limited |
Tags can be spoken aloud by some voices: always run the re-transcription diff. Pronunciation: respell in the TTS text only; phoneme tags exist only on specific models (verify). Intensity is realised mainly through text-level cues, not through wild settings.

## 5. Takes and joins
Paragraph-scale arcs per take (a whole section or part of one), within the request limit; never stitch tiny snippets. Use continuity parameters (previous/next text or request IDs) only if the model supports them. Join takes at the silence between scenes, with 5–10 ms fades, true silence at the voice's noise floor for `pauseBeforeMs/pauseAfterMs`, and no crossfade through words. Reject a take for: wrong or missing words, spoken tags, mispronounced names, a level or timbre jump against its neighbour (more than about 2 dB short-term loudness or an audible character change), emotion that contradicts the intent.

## 6. Timing write-back contract (stage 03 steps 4-6)
- `tools/align.py` aligns the final assembled audio against `spoken_script.txt` and gives word times; `alignment.json` stores them with scene indices, the engine used and its quality numbers. Each Short gets its own alignment of its own assembled audio (`tools/short_audio.py`).
- Scene visual windows are contiguous: `startS` = previous scene's `endS` (first scene 0); `endS` = midpoint of the silence between this scene's last word and the next scene's first word (last scene: last word end + `pauseAfterMs`, minimum 0.8 s).
- Lead-in: first word about 0.4–0.6 s after the start in the long video, 0.3 s or less in a Short. A transition's window is centred on the boundary and may be shifted by `transition.offsetMs` to land on a cue word.
- Short lines are separate takes that extend the first or last scene's visual window; they never create a boundary. Their durations go in `audio/shorts/<id>/lines.json` (`{"opening":{"file":"opening.wav","durationS":3.1},"closing":{…}}`), which `tools/make_allow.py` reads.

## 7. Audition (stage 03 step 3)
Synthesise the hardest passages (highest intensity, hardest names) and one neutral passage. Check alignment coverage, transcript diff and tag leakage, take-to-take level, and (advisory, if `librosa` is installed) a prosody proxy: pitch range in semitones and speaking rate per scene. An intensity-2 scene should show a wider range or a different rate than its intensity-0 neighbours; if not, change the text-level cues once. The proxy cannot prove an emotion sounds right, so produce `audio/review-reel.wav` (about 60 s: the opening, one peak, one quiet moment) for the creator to judge by ear.

## 8. Music and effects (the cue sheet)
Priority: voice intelligibility, then atmosphere, then spot effects. Music is optional and a valid answer is "none". Never put bass drops or dramatic risers under care/high material. Music under speech sits well below the voice (starting point about 12 dB under, by ear and by measurement), ducks around key words, and stops for the hardest explanations. An effect needs a reason: a reveal, an object action or a spatial move; one sound per movement is noise. `audio/cue-sheet.json`:
```json
{"scenes":[{"sceneId":"s03","music":{"action":"start|continue|duck|stop|none","file":"…","gainDb":-24},
            "sfx":[{"atWord":12,"file":"…","gainDb":-18,"reason":"the molecule scatters the beam"}],
            "silenceMs":1800}]}
```
Every music or effect file has a license entry in `credits.md` (H6). Code-synthesised pads and ticks are the last resort and are labelled lower quality.

## 9. Examples (illustrative, not templates)
- Reveal after explanation: `{intent:"hand over the answer", emotion:"quiet-wonder", intensity:2, pace:"slower", emphasisWords:["bigger"], pauseBeforeMs:500}`.
- Honest uncertainty: `{intent:"say what is not known", emotion:"matter-of-fact", intensity:0, pace:"steady", deliveryNotes:"no drama; the limit of knowledge is the point"}`.
- Human stake on care material: `{intent:"acknowledge", emotion:"tender", intensity:1, pace:"slower"}`.
