# SceneProgram v1

`SceneProgram` is the persistent visual intermediate representation introduced
in Math Animation 0.2. It is intended for shots whose teaching geometry must
survive across several transformations.

It is not a workflow graph and it does not contain live Manim objects. It is a
strict, JSON-serializable declaration that compiles deterministically to one
Manim `Scene` or `ThreeDScene`.

## Beat boundary

A `BeatSpec` must define exactly one of:

- `blocks`: the v0.1 vocabulary of self-contained, self-cleaning shots; or
- `scene_program`: persistent objects and coordinated action cues.

This keeps simple shots concise and preserves every v0.1 project.

## Object model

All objects have:

- A stable `id`.
- A three-component `position`.
- A `fixed_in_frame` flag.
- Optional aspect-specific position, scale, and relative-layout overrides.

The v1 object vocabulary is:

| Type | Purpose |
| --- | --- |
| `text` | Styled explanatory text or captions |
| `math_tex` | Addressable LaTeX parts with semantic color roles |
| `dot`, `line`, `arrow`, `circle`, `rectangle`, `polygon`, `polyline` | Common persistent geometry |
| `axes`, `function_graph`, `parametric_curve` | Plots and curves |
| `annotation`, `group` | Teaching labels and object collections |
| `tracked_point`, `connector`, `orbit_circle`, `trace` | Dependency-driven motion |
| `point_cloud` | Vectorized deterministic samples with named coordinate states |
| `parametric_surface` | Sampled and preflighted 3D surface |
| `scalar_field_footprint` | Sampled cells below a scalar threshold |
| `interval` | Open/closed measured one-dimensional interval |

`math_tex.formula_id` can bind an object to the mathematical ledger. When it
does, its `latex_parts` must exactly preserve the ledger formula.

## Vectorized point clouds

A point cloud declares:

1. A deterministic sample interval and count.
2. An initial scalar time value.
3. Ordered expression bindings.
4. One or more named coordinate states.
5. Its initial state.
6. Optional projection assertions.

Bindings can reference `i`, `t`, and earlier bindings. Expressions accept only:

- Numeric constants.
- Arithmetic.
- `pi` and Euler's constant `e` when `e` is not a declared binding.
- `sin`, `cos`, `tan`, `sqrt`, `exp`, `log`, and `abs`.

They cannot import modules, access attributes, index arbitrary values, invoke
unknown functions, or perform file/network operations. The compiler rewrites
approved functions to NumPy and evaluates all samples in vectorized form.
Every coordinate state is compiled as a function of time, so the same object
can be animated without regenerating source code.

The current hard limit is 10,000 points per cloud.

## Projection assertions

A projection assertion compares two selected coordinate pairs with
`numpy.allclose` before the scene begins. For example:

```json
{
  "id": "assert.exact-xz-shadow",
  "source_state": "exact-lift",
  "source_axes": ["x", "z"],
  "target_state": "shadow",
  "target_axes": ["x", "z"],
  "time_values": [0.0, 1.5, 4.0],
  "absolute_tolerance": 1e-9
}
```

This turns an explanatory claim such as “the lift projects exactly to the
original shadow” into a render-blocking invariant. When `time_values` is
present, the invariant is checked independently at every listed time. Without
it, the check uses the cloud's initial `time_value`.

## Action model

The v1 actions are:

| Action | Effect |
| --- | --- |
| `create` | Introduces one declared object |
| `transform_point_cloud` | Morphs a cloud to a named coordinate state |
| `animate_point_cloud_time` | Drives a named state through time with a `ValueTracker` |
| `fade_in` | Reintroduces an object that was already created |
| `fade_out` | Removes a visible object |
| `camera` | Changes a `ThreeDScene` camera pose |
| `move`, `scale`, `rotate`, `set_style` | Common persistent-object motion |
| `apply_matrix` | Checked 2×2 linear transformation |
| `transform_math` | `TransformMatchingTex` with a ledger-locked destination |
| `animate_tracker` | Drives dependency geometry through a scalar interval |

Actions live inside an `ActionCue`. A cue is either:

- `sequential`: action durations are summed; or
- `parallel`: every action shares one duration and one clock.

A parallel cue can transform geometry while the camera moves. It can contain at
most one camera action.

Each cue can use the same beat-relative, project-relative, beat-fraction, or
Nolan word anchor as a legacy block.

## Lifetime validation

The contract rejects:

- Duplicate object or cue IDs.
- Unknown action targets.
- Use before creation.
- Creating one object more than once.
- Point-state transforms on non-point-cloud objects.
- Unknown point states.
- Camera actions in a 2D scene.
- Parallel actions with different durations.
- Overlapping top-level cues.

Parallel behavior must be explicit inside one parallel cue.

## Artifacts

A compiled SceneProgram beat writes:

```text
visual_ir/<beat-id>.scene.json
source/<beat-id>.py
clips/<beat-id>.mp4
```

The run bundle also contains a standalone
`schemas/scene-program.schema.json`.

Export it directly with:

```bash
/opt/miniconda3/envs/mas/bin/python -m math_animation \
  schema --kind scene-program -o scene-program.schema.json
```

## Reference example

`examples/olin_scene_program.json` demonstrates:

- A 1,200-point vectorized cloud.
- The Olin definition chain.
- Flat shadow, exact lift, and cylindrical coordinate states.
- A checked xz-projection invariant.
- Fixed MathTex and caption layers.
- Parallel camera and point-cloud transforms.
- Standalone compilation, rendering, and composition.

`examples/olin_featured_project.json` is the fuller acceptance film. It
exercises 10,000-point density, a 5,000-point time-varying cloud, repeated
object re-entry, four-time projection checks, formula-ledger locks, camera and
geometry concurrency, and a 62-second multi-section edit.

## Deliberate v1 limits

The contract still deliberately excludes:

- Cross-beat live Manim object persistence; Nolan receives independently
  editable clips instead.
- General constraint solving. Common relative layout and authored aspect
  variants are supported, but arbitrary responsive composition is not.
- Unrestricted user Python in the normal path.
- An automatic repair agent. Review evidence is generated automatically; a
  planner or human decides the repair.
- A workflow engine inside the visual IR. `SceneProgram` remains durable data,
  not LangGraph state.

Those should be added as typed data and deterministic compilers. They should
not be introduced as arbitrary Python fields.
