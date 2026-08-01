# Nolan Integration Contract

## Ownership

Nolan owns:

- Script orchestration outside the mathematical reasoning module.
- TTS.
- Word-level alignment.
- Style-template authoring and storage.
- General GSAP motion blocks.
- Final video composition and delivery.

Math Animation owns:

- Mathematical prerequisite and claim artifacts.
- Formula and symbol semantics.
- Mathematical screenplay beats.
- Legacy Manim block selection.
- Persistent `SceneProgram` object/action plans for coordinated 3D shots.
- Deterministic Manim compilation.
- Manim-specific custom scenes when blocks are insufficient.
- Clip rendering and math-focused review.
- Expanded typed-template planning and structural pedagogy evidence.

## Inputs from Nolan

The eventual adapter needs four inputs:

1. Script or topic plus audience and duration constraints.
2. Narration audio path and word timestamps.
3. Style-template reference and payload.
4. Asset references Nolan has approved for this authoring job.

The temporary alignment adapter accepts:

```json
{
  "audio_path": "/job/audio/voice.wav",
  "utterances": [
    {
      "id": "beat.limit",
      "text": "Move the second point closer.",
      "words": [
        {"word": "Move", "start": 4.0, "end": 4.4},
        {"word": "closer", "start": 5.2, "end": 5.8}
      ]
    }
  ]
}
```

It also recognizes `segments`, `tokens`, `start_seconds`, `end_seconds`,
`start_time`, and `end_time`. This tolerance is temporary; the production
adapter should validate Nolan's exact versioned schema.

## Outputs to Nolan

Nolan should consume `timeline.json`, `style.lock.json`, `manifest.json`,
`pedagogy.json`, and the files under `clips/`.
`visual_ir/<beat-id>.scene.json` is an additional
inspectable artifact for SceneProgram beats; Nolan does not need to interpret it
to place the rendered clip.

Each timeline clip has:

- Stable `beat_id`.
- Manim `scene_class`.
- Generated source path.
- Expected media path.
- Project in and out times.
- Exact duration.
- Alpha flag.

Project-level timeline fields include frame rate, resolution, total duration,
and the original narration audio path.

## Media policy

Two delivery modes are supported by the contracts:

- Full-frame MP4 clips for self-contained mathematical shots.
- Transparent MOV clips for overlays Nolan will composite over its own stage.

Nolan and Math Animation must eventually agree on:

- Resolution and frame rate.
- Color space and transfer characteristics.
- Alpha codec.
- Audio sample rate and loudness target.
- Caption format.
- Transition-handle duration.
- Whether Nolan wants clean plates in addition to final clips.

These are render/delivery fields, not prompt instructions.

## Style adapter

Until Nolan is available, `StyleTemplateRef.raw` is preserved and a small
placeholder vocabulary is normalized. The production adapter should map Nolan
tokens into:

- Background and foreground.
- Typography.
- Semantic math colors.
- Line and grid treatments.
- Camera and motion presets.
- Caption treatment.
- Safe areas and density limits.

Semantic roles must remain distinct after mapping. Brand colors should not make
"changing" and "fixed" quantities visually indistinguishable.

## Suggested Nolan author-stage flow

```text
Nolan script
  -> math module planning/review
  -> Nolan TTS and alignment
  -> math module timing resolution
  -> legacy blocks or persistent SceneProgram
  -> Manim compilation/render
  -> Nolan receives clips + timeline + captions/stems
  -> Nolan mixes Manim clips with GSAP blocks and other assets
  -> Nolan final render
```

For a locked script, Nolan can invoke the math module after TTS. For co-authored
math explanations, Nolan should let the math planning pass propose script
changes before generating final speech.
