"""Video deconstruction — the inverse Director.

Given an ingested library video, recover its editorial plan: beats, the
script↔asset pairing rationale (in the evocative-b-roll operator vocabulary),
the tempo curve (in ``tempo_plan``'s energy/transition/motion_speed terms),
and the motion applied to assets (in the motion library's treatment
vocabulary) — assembled into a draft ``recovered_plan.json`` in the same
scene_plan schema the forward pipeline consumes.

Layering (mirrors the two style flows):
- **Facts** (``nolan.visual_facts``, Tier 1): shots + optical-flow motion +
  optional vision facts, persisted to the library's ``shots`` table.
- **Interpretation** (this package, Tier 2): editorial beats + operator
  classification via the text-LLM API, deterministic tempo recovery, draft
  plan assembly — written to ``video_deconstructions/<slug>/``.
- **Synthesis**: a dispatched Claude agent reads the extract (and frames) and
  writes ``breakdown.md`` + refines ``recovered_plan.json``.
"""

from .store import DeconstructionStore
from .extract import build_extract
from .tasks import deconstruction_synthesis_task

__all__ = ["DeconstructionStore", "build_extract", "deconstruction_synthesis_task"]
