---
id: organ.audio-mix
name: Audio mix / soundtrack organ
description: >
  The sound-design stage — a music bed whose energy arc matches the video, DUCKED under the
  narration with a real sidechain compressor (not a constant gain), plus transition SFX
  (whoosh / riser / data-punch hit). ONE integration point, `mix_soundtrack(final_video, plan)`,
  run AFTER assembly, shared by the Director pipeline, premium mode, and the segment builder.
  Read before touching music selection, VO ducking, the loudnorm/duck spec, the music library,
  or transition SFX. (The HF compose-first path ducks via `hyperframes/sfx_mix` + the sound
  umbrella instead — see below.)
kind: grammar
purpose: >
  Orient any soundtrack/mix task — the mix_soundtrack integration point, the real sidechain
  duck spec, music-library selection by energy arc, and the transition-SFX authoring.
status: active
version: 1
tier: organ
handoffs:
  - { process: director, stage: sound, gate: B }
uses:
  - common.sound-craft
documents:
  module: src/nolan/audio_mix.py
loaded_by: []
evals: []
---

# Audio mix / soundtrack organ (`src/nolan/audio_mix.py`)

The invisible half of a good essay. **ONE integration point** — `mix_soundtrack(final_video,
plan, …)` runs AFTER assembly, so the standard pipeline, premium mode, and the segment builder
all share it. Opt-in per project (zero surprise) via `project.yaml music:` (`auto` | a file path
| absent = no music); `music_gain_db` (default −14) and `sfx: false` tune it.

## The mix (real ducking, not a gain cut)

The soundtrack spec is authored (`author_soundtrack`), saved (`save_soundtrack`), then applied
(`mix_from_spec` / `mix_soundtrack`) as an ffmpeg graph:

- **loudnorm** the music to the target LUFS (spec `loudnorm_lufs`, default −16), then
- **`sidechaincompress`** the music UNDER the VO — a real compressor keyed off the narration
  (`duck` spec: `threshold 0.04 · ratio 4 · attack 25ms · release 400ms`), NOT a constant gain,
  so the bed breathes back up between phrases.

## Music selection — match the energy ARC

- Library: `projects/_library/music/`; optional `music.json` tags tracks
  `[{file, energy 0-1, mood, tags}]` (untagged → energy 0.5).
- `section_energies(plan)` reads the tempo system's per-scene energies; `select_track` picks the
  closest mean-energy track, looped/trimmed to length, 2s fade-in / 4s fade-out.

## Transition SFX

`ensure_whoosh` (band-swept pink noise = air movement, not static), `ensure_riser`, `ensure_hit`
(data-punch on data reveals via `_data_punch_events`). `author_sfx_cues` places ≤2 per section.
Gains are measured, not guessed (e.g. the 0.7-not-0.5 note = hi-band RMS at the seam).

## Invariant + verification

- **Runs after assembly** on the finished video — it never re-times anything.
- **Measure, don't eyeball** — verify a mix by band RMS at the seam + duration deltas (CLAUDE.md).

## Relationship to the HF sound path

This organ is the **Director / segment / premium** mixer (SOTA #1). The dominant **HF compose-first**
path ducks differently: render VO-only, then `hyperframes/sfx_mix` (`nolan hf-finish --duck`) applies
`sidechaincompress` per cue post-mix, driven by the **sound umbrella** registry (`common.sound-craft`,
`[[project_sound_sfx_module]]`). Same DSP idea (real sidechain, post-mix), different driver. For HF
work start at `[[pipeline.hyperframes]]`; use this organ for the Director/segment path.
