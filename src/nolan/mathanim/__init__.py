"""Math animation — the fourth typed SOURCE a NOLAN scene can be built from.

Beside media, data and document: a `math` scene declares a mathematical intent
(a template plus constrained parameters, or a typed stateful `SceneProgram`) and
a ledger of every formula it will display. The finish DAG resolves it into a
Manim clip mounted as that scene's video ground.

  authored              resolved                     mounted
  ---------------------------------------------------------------------------
  scene.type = "math"   nolan.mathanim.resolve       data.ground = {kind:video}
  data.template         -> ProjectSpec (adapter)     -> collect_video_grounds
  data.params           -> Manim source (engine)     -> inject_root_video
  data.formulas         -> clip in assets/math/      -> the composed frame paints
                                                        theme chrome over it

Layout:
  registry.py  the ONE template vocabulary (+ the shared validator)
  style.py     NOLAN theme -> Manim style tokens, with the legibility checks
  adapter.py   a scene -> ProjectSpec: the timing/ledger/pacing seam
  render.py    the subprocess boundary to the Manim env
  resolve.py   the finish-DAG step + the content-addressed clip cache
  gate.py      the math-provenance report the HARD gate reads

Manim and LaTeX live in a SEPARATE conda env (`D:\\env\\mas`) — see
`vendor/math-animation/CLAUDE.md`. Everything in this package except `render.py`
runs in the pipeline env with pydantic alone.
"""

__all__ = ["adapter", "gate", "registry", "render", "resolve", "style"]
