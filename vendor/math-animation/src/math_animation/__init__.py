"""Artifact-first mathematical animation authoring.

Attribute access is LAZY (PEP 562). The eager version of this file imported
``workflow`` (LangGraph) and ``model_provider`` (OpenAI) at package import, so
``from math_animation.contracts import ProjectSpec`` needed both installed —
even for a caller that only wants to validate and compile a screenplay.

NOLAN is exactly that caller: its pipeline env carries pydantic and nothing else
from this stack, and the whole authoring path (contracts -> math_validation ->
pedagogy -> timing -> blocks/scene_compiler -> compiler -> handoff -> cache)
needs only pydantic. Manim, LaTeX and the render subprocess live in a separate
env; LangGraph and OpenAI are optional extras nothing in NOLAN uses. Keeping
these imports lazy is what lets one checkout serve both.
"""

from typing import TYPE_CHECKING

from math_animation.version import __version__

__all__ = [
    "AuthoringPipeline",
    "BoundedRepairWorkflow",
    "OpenAIResponsesDecisionProvider",
    "ProjectSpec",
    "SceneProgram",
    "__version__",
]

# exported name -> the submodule that defines it (imported on first access)
_EXPORTS = {
    "ProjectSpec": "math_animation.contracts",
    "SceneProgram": "math_animation.contracts",
    "AuthoringPipeline": "math_animation.pipeline",
    "OpenAIResponsesDecisionProvider": "math_animation.model_provider",
    "BoundedRepairWorkflow": "math_animation.workflow",
}

if TYPE_CHECKING:  # keep type checkers and IDEs seeing the real symbols
    from math_animation.contracts import ProjectSpec, SceneProgram
    from math_animation.model_provider import OpenAIResponsesDecisionProvider
    from math_animation.pipeline import AuthoringPipeline
    from math_animation.workflow import BoundedRepairWorkflow


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value  # cache, so the import cost is paid once
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
