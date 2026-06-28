# NOLAN effect-analysis task

A user saved a clip from a source video and wants to know **what visual / motion
effect it uses** and **whether NOLAN can already reproduce it**.

## The clip
- Source video: `projects\US Economy\source\If The Economy Is F＊cked, Why Hasn’t It Crashed Yet？.mp4`
- In/out: 118.409675s → 119.242154s (0.8324790000000064s)
- Label: (none)
- Extracted clip file (watch motion via ffmpeg/your tools): `projects/_clips/clip_4d85395f/clip.mp4`
- Sample frames:
  - projects/_clips/clip_4d85395f/frames/frame_0001.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0002.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0003.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0004.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0005.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0006.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0007.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0008.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0009.jpg
  - projects/_clips/clip_4d85395f/frames/frame_0010.jpg

## What to do (in order)
1. **Inspect** the frames (and the clip file if you need finer motion detail —
   e.g. `ffmpeg -i projects/_clips/clip_4d85395f/clip.mp4 -vf fps=10 ...`). Describe the effect precisely:
   camera move, transition, text/graphic animation, color/filter, etc.
2. **Dedup against the existing motion library FIRST.** Check whether we already
   have it before proposing anything new:
   - Scene templates: `src/nolan/renderer/scenes/` (e.g. ken_burns, flashback,
     portrait_reveal, pull_quote, lower_third, comparison, timeline, …)
   - Effect primitives: `src/nolan/renderer/effects.py` (FadeIn/Out, Slide*,
     MoveTo, ScaleIn/Out, Pulse, Shake, Glitch, BlurIn/FocusPull, Glow*, Shadow*,
     Letterbox, Scanlines, ColorTint, VHSEffect, Reveal, RotateIn/Spin, …)
   - Render-service effects: `render-service/src/effects/`
   State clearly: **already covered** (name the template/effect) or **new**.
3. If **new**, assess **replicability**: can it be built from existing effect
   primitives / a new scene template? Give a concrete plan (which files, which
   primitives, rough difficulty). If not replicable, say why.

## Output
Write your findings to `projects/_clips/clip_4d85395f/effect_analysis.md` as markdown with sections:
**Effect**, **Dedup result**, **Replicable?**, **Plan**. Keep it concise and
actionable. (Follow the repo's "Promoting Techniques to NOLAN" convention if you
end up implementing it.)
