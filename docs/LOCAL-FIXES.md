# Local hardening pass — changes made to v3.1

This is an implementation patch, not a claim that the system is production-proven.
The existing engine architecture, commands, data schemas, and visual design logic are preserved.

## Corrections made

1. **Safe resumption:** `tools/pipeline.py` now hashes required output contents. A missing or corrupted cached MP4, WAV, trace, or JSON is regenerated rather than silently accepted. A command that returns success but omits a promised output fails.
2. **Correct voice cache dependencies:** changing `tools/voice_direction.py` invalidates the voice step; previously it could reuse old narration despite changed vocal direction logic.
3. **Prevent unapproved voice downgrades:** if ElevenLabs was approved and configured with an API key but no voice ID, auto mode returns BLOCKED rather than quietly using robotic Flite. When premium voice is not available or not approved, the documented free fallback remains.
4. **Accurate character ceiling:** the ElevenLabs ledger reserves the length of the actual speech payload, including any model-specific delivery tags. It no longer uses the shorter raw transcript length for those requests.
5. **Detect changed assets:** the render cache now fingerprints project assets, asset manifests, and custom visuals. Replacing a PNG at the same path is not silently ignored on resume.
6. **Safe project names:** `tools/new_project.py` rejects directory traversal and malformed duration ranges before creating folders.
7. **Safe demo instructions:** `INSTALL.md` no longer deletes `videos/demo` when running the example; demos get unique folders.
8. **Correct archive instructions:** setup examples now refer to the fixed archive instead of the old v3 name.
9. **Portable typography fallback:** no font binaries are redistributed. Default example projects use the browser's sans-serif font. If you already own the original archive, use `python3 tools/restore_fonts_from_original.py <original.zip>` to restore its licensed font files locally and select them in your style tokens.

## Tests actually run in this review environment

- Python bytecode compilation of changed core modules: PASSED.
- `pytest` selected voice direction tests + new hardening regression tests: **6 passed**.
- Bad project slug and reversed duration guard: **rejected as intended**.
- The SHA-256 cache check detects modified output contents: **PASSED**.

## What could not be tested here

- npm installation timed out in this environment; therefore the full TypeScript/Chromium suite and a new real MP4 render **were not run** as part of this patch.
- No live Higgsfield or ElevenLabs calls, paid operations, or long-form 5+ minute render were run.
- v3.1's original status and smoke videos remain historical evidence from its author, not proof of the new patch running end-to-end here.

## Run on your computer

1. Install Node 22+, Python 3.13 (recommended for pinned dependencies), ffmpeg and ffprobe.
2. From inside `youtube-system/`: `npm install && npx playwright install chromium`.
3. In a Python virtual environment: `pip install -r requirements.txt`.
4. Run `python3 tools/doctor.py` and `npm test` (full test suite).
5. In Claude Code, use `/make <your video idea>`. Approve any actual paid services separately when prompted.

**Important:** do not assume that passing machine checks proves emotional voice quality, beauty of transitions, or high viewer retention. A real long-form production is still the acceptance test.
