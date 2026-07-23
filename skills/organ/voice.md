---
id: organ.voice
name: Voice / voiceover organ
description: >
  The shared voiceover core — one TTS pipeline for the webUI and the pipeline. Per-section
  synthesis writes the beat-anchor wavs (`assets/voiceover/_work/sec_NNNN.wav`) that the whole
  render times itself to (narration owns duration), plus voice cloning from the voice library,
  the GPU lock it shares with ComfyUI, the speak-ready quality gate, and take versioning. Read
  this before touching voiceover synthesis, the `sec_*.wav` anchor contract, voice cloning, the
  quality gate, or the `nolan voiceover` CLI — or when a render's timing/narration looks wrong.
kind: grammar
purpose: >
  Orient any voiceover / narration task — the per-section anchor contract, cloning, the GPU
  lock, the speak-ready gate, take versioning, and where VO plugs into the HF finish DAG.
status: active
version: 1
tier: organ
handoffs:
  - { process: hyperframes, stage: voice, gate: B }
uses: []
documents:
  module: src/nolan/voice_pipeline.py
loaded_by: []
evals: []
---

# Voice / voiceover organ

One TTS pipeline (`src/nolan/voice_pipeline.py`), extracted so the `/voices` page, the
webUI op, and the pipeline's `voiceover` step all run the **same** code. It produces the
narration the entire video is timed to.

## The load-bearing contract (do not break)

- **Narration owns duration.** Per-section synthesis writes one wav per beat to
  `assets/voiceover/_work/sec_NNNN.wav`. These wavs ARE the beat anchors: the HF finish
  DAG's `sync-durations` step derives every frame's duration from them, and `word-sync`
  force-aligns each scene to the spoken word. Change how sections are split or numbered and
  you move every downstream anchor — treat `sec_NNNN` numbering as a contract.
- **The speak-ready quality gate blocks** — voiceover that fails the gate raises, it does not
  ship silently (`voiceover failed the quality gate — …`).

## What lives here (`voice_pipeline.py`)

| Concern | Entry |
|---|---|
| Per-section synthesis (writes `sec_*.wav`) | `synthesize_sections()` |
| Build TTS items (cloning ref_audio/ref_text, instruct, speed) | `build_tts_items()` / `_tts_item()` |
| Sentence/chunk packing (diffusion TTS degrades on long input) | `_split_sentences()` / `_split_to_chunks()` |
| Finalize (trim, measure, wpm) + provenance | `finalize_sections()` / `_write_provenance()` |
| Take versioning (retake without losing prior) | `archive_current_take()` / `list_takes()` / `restore_take()` |
| Package full mp3 from ordered sections | `concat_wavs_to_mp3()` |

## Runtime facts (these bite)

- **GPU lock**: synthesis serializes with ComfyUI via `get_gpu_lock()` — a voiceover run
  queues behind a render/gen and vice-versa. Prefer CPU work (rembg cutout) when the GPU is busy.
- **Voice cloning**: clone from `voices/<id>/sample.wav` + `ref_text`; the library lives under
  the voice library (`/voices` page browses project + HF VOs).
- **CLI**: `nolan voiceover` (per-section synthesis + retake + take versioning). See also `/tts`.
- **TTS backend**: OmniVoice runs in a separate CUDA env (`D:\env\omnivoice`) via subprocess —
  see `[[project_omnivoice_tts]]` and its live-probed limits (`instruct` yields no audio; no seed).

## Where it plugs into the pipeline

`voiceover` step → writes `sec_*.wav` → HF finish DAG `sync-durations` (durations FROM the VO)
→ `word-sync` (place scenes on the spoken word). See `[[pipeline.hyperframes]]` for the DAG.
