# math-animation — vendored into NOLAN

Upstream: `github.com/SeraphicYuan/Animation-Math` @ v0.7.1 (`a5956b7`). This is a
**vendored copy**, not a submodule: NOLAN owns it now and the deferred work in
`docs/DEFERRED_NOLAN_WORK.md` gets done here.

**Do not author math scenes by editing this package.** The NOLAN-facing surface is
the `math` composer block and `src/nolan/mathanim/` — see the `organ.math-animation`
skill. This directory is the ENGINE behind that adapter.

## Two interpreters, on purpose

The whole authoring path — contracts → math_validation → pedagogy → timing →
blocks/scene_compiler → compiler → handoff → cache — imports **only pydantic**.
`numpy` appears solely inside *generated* Manim source; `PIL` only in `review.py`;
`langgraph` only in `workflow.py`; `manim` is never imported, only probed and
subprocessed. So:

| env | python | has | runs |
|---|---|---|---|
| `nolan` | `D:\env\nolan\python.exe` | pydantic, Pillow | validate · compile · pedagogy · review · cache |
| `mas` | `D:\env\mas\python.exe` | manim 0.20.1, MiKTeX, dvisvgm | the Manim render subprocess + LaTeX preflight |

`AuthoringPipeline(python_executable=...)` selects the second one. Everything
else stays in-process, so NOLAN's `numpy<2.3` / `Pillow<12` pins never meet
Manim's dependency stack.

```bash
D:\env\nolan\Scripts\pip.exe install -e vendor/math-animation
D:\env\mas\Scripts\pip.exe install -e "vendor/math-animation[render]"
D:\env\mas\python.exe -m math_animation doctor      # all five must be present
```

Always `python -X utf8` (NOLAN rule — cp1252 corrupts the → · characters and the
LaTeX these artifacts carry).

## The changes from upstream (keep this list honest)

Everything else is byte-identical to v0.7.1, so upstream stays mergeable and the
golden-hash compatibility gates in `tests/golden/` still hold.

**Lazy optional extras** — so one checkout serves both envs:

1. `src/math_animation/__init__.py` — lazy PEP-562 `__getattr__`. Eager imports of
   `workflow` (LangGraph) and `model_provider` (OpenAI) made
   `from math_animation.contracts import ProjectSpec` fail in an env that has
   neither. That was the one hard blocker to a single shared checkout.
2. `workflow.py` — LangGraph imported inside `_build_graph`, not at module
   scope. `RepairPolicy` is a plain pydantic model whose FROZEN v0.5 golden hash
   must be checkable anywhere; a module-level import made a schema-compatibility
   test depend on a graph runtime it never touches.
3. `cli.py` — `BoundedRepairWorkflow` imported inside `_cmd_repair`, matching the
   file's existing lazy-provider idiom, so every other command still runs
   without the extra.
4. `pyproject.toml` — `langgraph` moved from base deps to a `[workflow]` extra.

**The render-worker boundary** — the isolated worker `docs/ARCHITECTURE.md` asks for:

5. `renderer.py` / `toolchain.py` / `preflight.py` — an optional
   `python_executable` threads through `ManimRenderer`, `manim_available()`,
   `candidate_bin_dirs()`, `executable_path()`, `subprocess_environment()`,
   `runtime_executable_path()` and `validate_latex()`. Default is
   `sys.executable`, so standalone behaviour is unchanged. `candidate_bin_dirs`
   also learned the Windows conda layout (`Scripts/`, `Library/bin/`) and
   `executable_path` learned `.exe`.

**Tests that were macOS-only** — both failed on Windows in pristine upstream too
(verified against the untouched clone before touching anything):

6. `tests/test_toolchain.py` split PATH on a hardcoded `":"` while
   `subprocess_environment` joins with `os.pathsep`. Fixed to split the way it
   joins, plus a new test that the render interpreter's bin dir wins when one is
   named.
7. `tests/test_toolchain_tex_cache.py` asserted `TEXMFVAR`, which is set only
   inside the Homebrew TeX Live branch. Now skipped where that root is absent,
   with a companion test asserting the other direction — that no TeX override is
   invented pointing at a path that does not exist (MiKTeX needs its own config
   left alone).
8. `tests/test_repair.py` — the two LangGraph control-plane tests carry a
   `@requires_langgraph` skipif and import lazily; the four typed-repair PLANNER
   tests keep running without the extra.

9. `CLAUDE.md` (this file), `AGENTS.md`, and the README's env block — were macOS
   conda paths.

Baseline in the `nolan` env: **68 passed, 3 skipped**, `validate_examples.py`
validates 21 projects.

`artifacts/*.mp4|mov|png` were **not** vendored — 12 MB of upstream acceptance
evidence, regenerable by `scripts/run_*.py`. The JSON reports beside them were
kept, because those are the record.

## Contracts that must not drift

- `ProjectSpec v1`, `SceneProgram v1` and the v0.3–v0.7 goldens are frozen.
  Breaking either needs a new `schema_version`, never an in-place edit.
- No NOLAN or provider fields in the canonical models — adapters translate
  (`src/nolan/mathanim/adapter.py` is NOLAN's).
- `custom_scene` (arbitrary Python) is refused at NOLAN's authoring gate and
  must stay refused: it is an isolated-worker escape hatch, and NOLAN has no
  isolated worker.

## Verify

```bash
D:\env\nolan\python.exe -X utf8 -m pytest -q          # from vendor/math-animation
D:\env\nolan\python.exe -X utf8 scripts/validate_examples.py
```
