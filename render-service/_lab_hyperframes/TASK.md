# Hyperframes lab test — script + finished VO in, THEIR process does the rest

You are evaluating HeyGen's Hyperframes as a full authoring+rendering
pipeline. The test: given only our script and finished voiceover, follow
HYPERFRAMES' OWN creative process end to end (design, visuals, pacing) —
so we can compare what their workflow produces against what NOLAN produced
from the same inputs. Work ONLY inside `render-service/_lab_hyperframes/`.
Do NOT touch NOLAN plans/projects. Do NOT follow NOLAN's video pipeline for
the authoring — this run is deliberately "their way".

START with the `/hyperframes` router skill (installed in this repo), let it
route (script + finished narration → likely /faceless-explainer), and then
follow the skills' process faithfully: their design specs, beat planning,
scene blueprints, animation rules. Where their process makes a design
decision, take THEIR default — do not import NOLAN taste.

## Inputs (in ./inputs/)
- script.md — the narration script, 2 sections ("beats")
- sec_0000.wav (67.76s) + sec_0001.wav (91.76s) — the FINISHED voiceover,
  one per beat, in order. Timing authority. Do NOT regenerate narration.
- scene_*.png — optional stills from our pipeline; use only if their
  process calls for real imagery and these fit.

## Assets policy
Follow their /media-use flow first. If it needs models/keys we don't have,
record it under "## BLOCKED" in REPORT.md and fall back to:
- NOLAN picture search: hub API http://127.0.0.1:8011/api/images/search?q=...
- NOLAN ComfyUI generation (krea2): D:\ClaudeProjects\NOLAN docs; ComfyUI
  must be reachable at 127.0.0.1:8080 (if it is not running, record BLOCKED
  — the human can start it).
- BGM/SFX: their catalog/generation if available; else note the lack.

## Hard requirements
1. NARRATION OWNS DURATION: beat 1 spans exactly sec_0000.wav, beat 2
   exactly sec_0001.wav; total 159.5s (+/- 1s); wavs play unmodified.
2. Render `out/final.mp4` (1920x1080, 30fps).
3. DETERMINISM: render again to `out/final_repeat.mp4`; record both SHA256
   in REPORT.md.
4. REPORT.md: route taken, design decisions THEIR process made, assets used
   and where they came from, every failure/retry, wall-clock authoring and
   render times, surprises, and "## BLOCKED" for anything you lacked.
5. Loud failures — never silently approximate a requirement.

## Environment
- node v22.12.0 (C:\Program Files\nodejs), npx available. Pin versions.
- ffmpeg: "D:\Program Files\ImageMagick-7.1.1-Q16-HDRI\ffmpeg.exe"; fallback
  D:\env\nolan\python.exe -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
