# Featured Olin stress test

The v0.2 acceptance film is authored in
`examples/olin_featured_project.json`. It is a 62-second, caption-led
explanation derived from the Olin construction featured by Math-To-Manim.
Every visual and transition is expressed through `SceneProgram`; custom Python
is not enabled.

## Teaching sequence

1. Present the compact source expression.
2. Expand the dependent `k → e → d → c → q` coordinate recipe.
3. Render all 10,000 planar samples, then animate a 5,000-point working cloud.
4. Add an exact depth coordinate and inspect it with a moving 3D camera.
5. Return to the front view and state the checked projection identity.
6. Contrast the exact lift with a time-varying cylindrical interpretation.
7. Close with the formula chain, planar shadow, and lifted cloud together.

## Acceptance matrix

| Risk | Exercise | Result |
| --- | --- | --- |
| Dense geometry | 10,000-point static reveal | Pass |
| Per-frame work | 5,000 points recomputed through two time animations | Pass |
| Stateful visuals | One cloud survives transforms, fades, and re-entry | Pass |
| 3D orchestration | Geometry transforms and time updates run with camera moves | Pass |
| Mathematical integrity | Exact xz projection checked at four time values | Pass |
| Formula drift | Four displayed formulas are locked to the math ledger | Pass |
| Typography | Per-object fonts and maximum widths | Pass |
| Timeline | 62-second authored scene, 1,496 H.264 frames at 24 fps | Pass |
| Composition | Standalone 1280×720 yuv420p MP4 | Pass |
| Decoder integrity | Full FFmpeg decode with no reported errors | Pass |
| Visual QA | Stable keyframes inspected; one multiline defect found and repaired | Pass |

## Reproduce

```bash
PYTHONPATH=src /opt/miniconda3/envs/mas/bin/python -m math_animation \
  validate examples/olin_featured_project.json

PYTHONPATH=src /opt/miniconda3/envs/mas/bin/python -m math_animation \
  compile examples/olin_featured_project.json \
  --runs-dir runs --render --compose
```

The checked-in review artifacts are:

- `artifacts/olin_featured_stress_test.mp4`
- `artifacts/olin_featured_stress_test_keyframes.png`

## Scope of the result

This proves that the typed IR and deterministic compiler can carry a substantial
featured explainer. It does not yet prove automated pedagogy planning,
narration quality, Nolan style fidelity, projection rays, surfaces, or
cross-beat object persistence. Nolan TTS and word timestamps can be attached
later without changing the visual object model.
