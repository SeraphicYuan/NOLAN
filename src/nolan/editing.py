"""Editing umbrella — cutting-rhythm techniques as a declarative registry.

The module-contract home (CLAUDE.md) for editing decisions: each technique is
a registry entry (purpose + when_to_use + constraints), AUTHORED as data on
the plan (scene fields / project.yaml keys), VALIDATED here, and EXECUTED in
the premium render path. Mirrors nolan/motion/registry.py at smaller scale.

The sync contract is the legality gate for this umbrella: every technique
declares `duration_preserving`. Narration owns duration, so techniques that
stretch or compress time (speed ramps, freeze frames, overlap dissolves that
shorten the cut) are inadmissible inside narration spans — an entry with
duration_preserving=False documents WHY it isn't offered rather than being
silently absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class EditTechnique:
    id: str
    purpose: str                    # what it does (one line)
    when_to_use: str                # the craft guidance an agent needs to pick it
    scope: str                      # "boundary" | "scene" | "project"
    authored_by: str                # which field/artifact carries the decision
    params: Dict[str, str] = field(default_factory=dict)   # name -> doc
    duration_preserving: bool = True
    executor: str = ""              # where the decision becomes pixels/samples


TRANSITIONS = ("cut", "dissolve", "fade")   # mirrors nolan.tempo_plan._TRANSITIONS

REGISTRY: List[EditTechnique] = [
    EditTechnique(
        "j-cut",
        purpose="Pull an internal cut earlier so the next image arrives while "
                "the previous sentence is still finishing.",
        when_to_use="Default on for continuous narration. Kills the "
                    "cut-on-sentence-pause AI tell. Only applies when the "
                    "incoming scene opens on imagery — a text card's reveal "
                    "waits for its word cue, so it keeps a straight cut. "
                    "Section edges never move (beat anchors are sacred).",
        scope="boundary",
        authored_by="project.yaml `j_cut_frames` (default 12, 0 disables)",
        params={"j_cut_frames": "frames to pull each eligible internal cut "
                                "earlier (int, default 12 ≈ 0.4s at 30fps)"},
        duration_preserving=True,
        executor="nolan.premium_render.build_section_job",
    ),
    EditTechnique(
        "shot-list",
        purpose="Cut one scene's narration window into several camera-toured "
                "stills (editors cut in shots, not sentences).",
        when_to_use="Long narration spans (>6s) over a single still read as "
                    "static; the deconstruction corpus shows 2-4s shots under "
                    "longer spans. Weight shots by importance; `place` aims "
                    "the camera like the nine-dot tray. Windows too small for "
                    "every shot drop trailing shots rather than squeezing any "
                    "below ~0.8s.",
        scope="scene",
        authored_by="scene.shots `[{src, place?, weight?, caption?}]`",
        params={"src": "image path (absolute or project-relative), required",
                "place": "[x, y] in 0..1 — camera push target (nine-dot "
                         "convention), optional",
                "weight": "relative share of the scene window (number > 0, "
                          "default 1)",
                "caption": "reserved for montage captions, optional"},
        duration_preserving=True,
        executor="nolan.premium_render._expand_shots",
    ),
    EditTechnique(
        "transition-in",
        purpose="How a scene ENTERS: hard cut, or a short opacity ramp from "
                "the theme background (dissolve ≈ 0.27s, fade ≈ 0.47s).",
        when_to_use="Authored by the Editorial Arc pass from the energy arc: "
                    "fade under ~0.35 energy (contemplative), dissolve to "
                    "~0.55, cut above (urgent). Override per scene when a "
                    "beat needs a softer or harder landing than its energy "
                    "suggests. True overlap dissolves are NOT offered — they "
                    "shorten the cut and narration owns duration.",
        scope="boundary",
        authored_by="scene.transition `cut|dissolve|fade` (nolan.tempo_plan)",
        params={"transition": "one of cut | dissolve | fade — how this scene "
                              "enters (first sub-step only; a section's first "
                              "scene always hard-cuts with its beat anchor)"},
        duration_preserving=True,
        executor="nolan.premium_render.build_section_job -> Chapter "
                 "transitionIn",
    ),
]

BY_ID: Dict[str, EditTechnique] = {t.id: t for t in REGISTRY}


# --- validation (the deterministic gate for authored editing fields) -----------

def validate_scene_editing(scene: Dict[str, Any]) -> List[str]:
    """Structural problems with a scene's authored editing decisions.

    Loud where the executors are lenient: _resolve_shots silently skips a
    malformed shot (render-must-not-crash), this names it (authoring gate).
    """
    problems: List[str] = []
    sid = scene.get("id", "?")

    shots = scene.get("shots")
    if shots is not None:
        if not isinstance(shots, list):
            problems.append(f"{sid}: shots must be a list, got "
                            f"{type(shots).__name__}")
        else:
            for i, sh in enumerate(shots):
                if not isinstance(sh, dict) or not sh.get("src"):
                    problems.append(f"{sid}: shots[{i}] needs a src")
                    continue
                place = sh.get("place")
                if place is not None:
                    ok = (isinstance(place, (list, tuple)) and len(place) == 2
                          and all(isinstance(v, (int, float))
                                  and 0.0 <= v <= 1.0 for v in place))
                    if not ok:
                        problems.append(f"{sid}: shots[{i}].place must be "
                                        "[x, y] with 0..1 values")
                w = sh.get("weight")
                if w is not None:
                    if not isinstance(w, (int, float)) or w <= 0:
                        problems.append(f"{sid}: shots[{i}].weight must be a "
                                        "number > 0")

    tr = scene.get("transition")
    if tr is not None and tr not in TRANSITIONS:
        problems.append(f"{sid}: transition {tr!r} not in "
                        f"{'|'.join(TRANSITIONS)}")
    return problems


def validate_plan_editing(plan: Dict[str, Any]) -> List[str]:
    """validate_scene_editing over every scene of a raw plan dict."""
    problems: List[str] = []
    for scenes in (plan.get("sections") or {}).values():
        if isinstance(scenes, list):
            for s in scenes:
                if isinstance(s, dict):
                    problems.extend(validate_scene_editing(s))
    return problems
