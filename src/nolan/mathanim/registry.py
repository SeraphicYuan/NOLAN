"""The math-template registry — the ONE vocabulary a `math` scene may author.

A math scene names a template and fills constrained parameters. It never carries
Manim source: `custom_scene` is the engine's isolated-worker escape hatch, NOLAN
has no isolated worker, and the authoring gate refuses it by name.

This module is the single home for that vocabulary, in the shape the module
contract asks for (`purpose` + `when_to_use` + constraints). Four consumers read
it and NONE keeps a private copy — that is the `_GROUND_BLOCKS` fork
(docs/WIRING_CHECKLIST.md #4) this file exists to avoid:

  * `bridge/author.py`            — the authoring gate (refuses an unknown template)
  * `bridge/catalog.json`         — what the authoring agent discovers
  * `nolan/mathanim/adapter.py`   — builds the ProjectSpec from the params
  * `skills/organ/math-animation.md` — where an agent learns when to reach for one

`tests/test_mathanim.py` re-derives the catalog entry and the skill's template
list from here and fails on drift.

FORMULA REFERENCES. Every LaTeX a template displays is an INDEX into the scene's
own `data.formulas` ledger, never an inline string. That is what makes the
math-provenance gate cheap and total: a formula on screen either traces to a
ledger entry the author wrote down, or it does not ship. It mirrors the engine's
own source-grounding gates, which exist to stop a model inventing an equation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# --- parameter kinds -------------------------------------------------------------------------
# Deliberately small. A kind that only one template needs is a sign the template
# wants its own contract, not that the vocabulary should grow.
FORMULA_REF = "formula_ref"      # int index into data.formulas
FORMULA_REFS = "formula_refs"    # list[int], each an index into data.formulas
TEXT = "text"                    # short display string
EXPRESSION = "expression"        # a plottable expression in x, e.g. "0.25*x**2"
NUMBERS = "numbers"              # list[float]
TEXTS = "texts"                  # list[str]
RANGE = "range"                  # (min, max, step)
NUMBER = "number"                # float
OBJECT = "object"                # a nested typed structure (only `scene_program.program`)


@dataclass(frozen=True)
class Param:
    name: str
    kind: str
    doc: str
    required: bool = False
    min_len: Optional[int] = None
    max_len: Optional[int] = None


@dataclass(frozen=True)
class MathTemplate:
    id: str
    purpose: str
    when_to_use: str
    not_for: str
    params: Tuple[Param, ...]
    # how many ledger formulas this template needs before it can be authored at all
    min_formulas: int = 0
    # Every template is duration_preserving: the engine's compiler pads the scene
    # to exactly `beat.duration_seconds` and REFUSES when the animation needs more
    # (compiler.py / scene_compiler.py). Nothing here can stretch a narration span.
    constraints: Tuple[str, ...] = ("duration_preserving",)

    def param(self, name: str) -> Optional[Param]:
        return next((p for p in self.params if p.name == name), None)


TEMPLATES: Dict[str, MathTemplate] = {
    "title_card": MathTemplate(
        id="title_card",
        purpose="A typeset title (and optional subtitle) in the essay's theme, "
                "rendered by Manim so it sits in the same visual register as the "
                "mathematics around it.",
        when_to_use="Opening a mathematical section when the surrounding beats are "
                    "Manim scenes and an HTML `statement` would read as a different film.",
        not_for="A normal essay title or section card — the `statement` / `hero` blocks "
                "are cheaper, themed, and do not cost a Manim render.",
        params=(
            Param("title", TEXT, "the headline", required=True),
            Param("subtitle", TEXT, "an optional second line"),
        ),
    ),
    "equation_reveal": MathTemplate(
        id="equation_reveal",
        purpose="Write ONE equation onto the frame, part by part, with optional "
                "semantic roles colouring each part.",
        when_to_use="The beat introduces a single formula and the viewer needs to read "
                    "it once, cleanly. The default for 'here is the equation'.",
        not_for="Showing a DERIVATION (use equation_sequence) or two formulas side by "
                "side (use concept_comparison).",
        params=(
            Param("formula", FORMULA_REF, "which ledger formula to write", required=True),
            Param("part_roles", TEXTS,
                  "one semantic colour role per latex part: primary / changing / fixed / "
                  "positive / negative / muted. Empty means one uniform colour."),
            Param("caption", TEXT, "a short line under the equation"),
        ),
        min_formulas=1,
    ),
    "equation_transform": MathTemplate(
        id="equation_transform",
        purpose="Morph one equation into another, matching the parts that survive so "
                "the eye follows what actually changed.",
        when_to_use="ONE algebraic step where the point is the change itself — "
                    "factoring, substituting, rearranging.",
        not_for="Three or more steps (use equation_sequence — it keeps one persistent "
                "object across the whole derivation instead of restarting each time).",
        params=(
            Param("from", FORMULA_REF, "the starting formula", required=True),
            Param("to", FORMULA_REF, "the resulting formula", required=True),
            Param("caption", TEXT, "a short line naming the move"),
        ),
        min_formulas=2,
    ),
    "equation_sequence": MathTemplate(
        id="equation_sequence",
        purpose="Transform ONE persistent, ledger-bound formula through three to six "
                "authored steps — the derivation as a single continuous object.",
        when_to_use="A multi-step derivation. This is the workhorse of a maths explainer: "
                    "completing the square, solving for x, simplifying an expression.",
        not_for="A single formula (equation_reveal) or a single step (equation_transform).",
        params=(
            Param("steps", FORMULA_REFS,
                  "3-6 ledger formula indices, in the order they are derived",
                  required=True, min_len=3, max_len=6),
            Param("at", TEXTS,
                  "OPTIONAL: one short spoken phrase per step AFTER the first, so each "
                  "step lands on the words that describe it ('show it as you say it'). "
                  "Omit and the steps spread evenly across the beat."),
        ),
        min_formulas=3,
    ),
    "concept_comparison": MathTemplate(
        id="concept_comparison",
        purpose="Two authored formulas side by side with optional labels; stacks "
                "vertically in portrait.",
        when_to_use="The beat argues that two forms describe the same thing, or "
                    "contrasts a before and an after — standard form vs vertex form, "
                    "the general case vs the special case.",
        not_for="More than two formulas, or a comparison of non-mathematical ideas "
                "(use the HTML `comparison` block).",
        params=(
            Param("left", FORMULA_REF, "the left/upper formula", required=True),
            Param("right", FORMULA_REF, "the right/lower formula", required=True),
            Param("left_label", TEXT, "a label under the left formula (<= 32 chars)"),
            Param("right_label", TEXT, "a label under the right formula (<= 32 chars)"),
        ),
        min_formulas=2,
    ),
    "function_plot": MathTemplate(
        id="function_plot",
        purpose="Draw axes and trace one function's graph across them.",
        when_to_use="The beat is about the SHAPE of a relationship — where it turns, "
                    "grows, crosses zero.",
        not_for="Plotting DATA (bind a dataset to the HTML `chart` block instead — it is "
                "themed, cheaper, and provenance-gated). This is for a function you can write.",
        params=(
            Param("expression", EXPRESSION,
                  "the function of x in Python syntax, e.g. '0.25*x**2 - 3'", required=True),
            Param("x_range", RANGE, "[min, max, step] for the x axis"),
            Param("y_range", RANGE, "[min, max, step] for the y axis"),
            Param("label", FORMULA_REF, "a ledger formula to caption the curve with"),
            Param("role", TEXT, "semantic colour role for the curve (default: primary)"),
        ),
    ),
    "number_line": MathTemplate(
        id="number_line",
        purpose="A number line with marked values and optional labels.",
        when_to_use="Locating quantities on one axis: roots, an interval, a bound, "
                    "where a limit is heading.",
        not_for="A comparison of magnitudes across categories (use the HTML `scale` block).",
        params=(
            Param("values", NUMBERS, "the values to mark", required=True, min_len=1),
            Param("labels", TEXTS, "one label per value, or empty"),
            Param("x_range", RANGE, "[min, max, step] for the line"),
            Param("role", TEXT, "semantic colour role for the marks (default: primary)"),
        ),
    ),
    "secant_to_tangent": MathTemplate(
        id="secant_to_tangent",
        purpose="Sweep a secant line into a tangent as the interval shrinks — the "
                "limit definition of the derivative, animated.",
        when_to_use="Introducing derivatives, rates of change, or any 'as h goes to "
                    "zero' argument.",
        not_for="Anything that is not this specific limit argument.",
        params=(
            Param("expression", EXPRESSION, "the curve, e.g. '0.25*x**2'", required=True),
            Param("x0", NUMBER, "the point the tangent is taken at"),
            Param("h_start", NUMBER, "the starting interval width (> 0)"),
            Param("h_end", NUMBER, "the final interval width (> 0, smaller than h_start)"),
            Param("x_range", RANGE, "[min, max, step] for the x axis"),
            Param("y_range", RANGE, "[min, max, step] for the y axis"),
            Param("caption", TEXT, "a short line naming what is happening"),
        ),
    ),
    "scene_program": MathTemplate(
        id="scene_program",
        purpose="The typed stateful visual IR — persistent objects that keep their "
                "identity across cues: 3D surfaces, point clouds, tracked points, "
                "parametric curves, matrix transforms, assertions.",
        when_to_use="A shot no template above can express, where objects must PERSIST "
                    "and coordinate: a determinant deforming an area, Fourier epicycles, "
                    "a Jacobian acting on a neighbourhood, a potential landscape.",
        not_for="Anything a template above covers — a template is faster, responsive, "
                "and already has render fixtures. This is the bespoke tier, not the "
                "default one. It is still TYPED: it is not a hole for Python.",
        params=(
            Param("program", OBJECT,
                  "a SceneProgram object (schema: `math-animation.scene-program.v1`); "
                  "validated by round-tripping through the engine's contract",
                  required=True),
        ),
    ),
}

TEMPLATE_IDS: Tuple[str, ...] = tuple(TEMPLATES)

# Semantic colour roles a `part_roles` / `role` param may name. They come from the
# engine's StyleTokens.semantic_colors, and `nolan.mathanim.style` guarantees
# `changing` and `fixed` stay perceptually distinct after a theme is mapped onto
# them — a brand palette that collapses those two makes a derivation unreadable.
SEMANTIC_ROLES: Tuple[str, ...] = (
    "primary", "secondary", "changing", "fixed", "positive", "negative",
    "foreground", "muted",
)


def template(name: str) -> Optional[MathTemplate]:
    return TEMPLATES.get(name)


def catalog_entry() -> Dict[str, Any]:
    """The `math` block's authoring documentation, GENERATED from this registry.

    `bridge/catalog.json` carries a copy so the bridge stays importable without
    NOLAN on the path; `tests/test_mathanim.py` regenerates it and fails on drift.
    A hand-maintained slice of an inventory is pitfall #5.
    """

    return {
        "templates": {
            name: {
                "purpose": t.purpose,
                "when_to_use": t.when_to_use,
                "not_for": t.not_for,
                "min_formulas": t.min_formulas,
                "params": {
                    p.name: (
                        f"{p.kind}{' (required)' if p.required else ''} — {p.doc}"
                    )
                    for p in t.params
                },
                "constraints": list(t.constraints),
            }
            for name, t in TEMPLATES.items()
        },
        "semantic_roles": list(SEMANTIC_ROLES),
    }


# --- validation ------------------------------------------------------------------------------
# ONE validator, called by the authoring gate (bridge/author.py) and again by the
# resolver before it spends a Manim render. A gate that accepts what the resolver
# then refuses is the phantom-field class from docs/WIRING_CHECKLIST.md #1.

_RESERVED_DATA_KEYS = {
    # chrome + plumbing the composer paints or the resolver stamps; not template params
    "template", "params", "formulas", "objective", "kicker", "title", "caption",
    "source", "ground", "_math", "at", "cue", "_field_cues",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_param(p: Param, value: Any, n_formulas: int, where: str) -> List[str]:
    errs: List[str] = []

    def bad(msg: str) -> None:
        errs.append(f"{where}.params.{p.name}: {msg}")

    if p.kind == FORMULA_REF:
        if not isinstance(value, int) or isinstance(value, bool):
            bad(f"must be an integer index into data.formulas, got {value!r}")
        elif not 0 <= value < n_formulas:
            bad(f"index {value} is outside data.formulas (has {n_formulas})")
    elif p.kind == FORMULA_REFS:
        if not isinstance(value, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            bad("must be a list of integer indices into data.formulas")
        else:
            if p.min_len is not None and len(value) < p.min_len:
                bad(f"needs at least {p.min_len} entries, got {len(value)}")
            if p.max_len is not None and len(value) > p.max_len:
                bad(f"takes at most {p.max_len} entries, got {len(value)}")
            for v in value:
                if not 0 <= v < n_formulas:
                    bad(f"index {v} is outside data.formulas (has {n_formulas})")
    elif p.kind in (TEXT, EXPRESSION):
        if not isinstance(value, str) or not value.strip():
            bad("must be a non-empty string")
    elif p.kind == TEXTS:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            bad("must be a list of strings")
    elif p.kind == NUMBERS:
        if not isinstance(value, list) or not value or not all(_is_number(v) for v in value):
            bad("must be a non-empty list of numbers")
    elif p.kind == NUMBER:
        if not _is_number(value):
            bad("must be a number")
    elif p.kind == OBJECT:
        # shape only — the real check is `_validate_scene_program`, which borrows
        # the engine's own contract rather than growing a second one here
        if not isinstance(value, dict) or not value:
            bad("must be a non-empty object")
    elif p.kind == RANGE:
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 3
            or not all(_is_number(v) for v in value)
        ):
            bad("must be [min, max, step]")
        elif value[0] >= value[1]:
            bad(f"min {value[0]} must be below max {value[1]}")
        elif value[2] <= 0:
            bad(f"step {value[2]} must be positive")
    return errs


def validate_scene_data(data: Any, where: str = "math") -> List[str]:
    """Every reason this `math` scene cannot be built, as human-readable strings.

    Empty list means the scene is authorable. This checks SHAPE and REFERENCES;
    whether the mathematics itself is sound is `gate.py`'s question, and whether
    it renders is the engine's.
    """

    errs: List[str] = []
    if not isinstance(data, dict):
        return [f"{where}: data must be an object"]

    name = data.get("template")
    tpl = TEMPLATES.get(name) if isinstance(name, str) else None
    if tpl is None:
        return [
            f"{where}: data.template {name!r} is not a math template "
            f"{sorted(TEMPLATES)}"
        ]

    # Arbitrary Python never enters NOLAN. The engine gates `custom_scene` behind
    # --allow-custom-python AND an asserted isolated renderer; NOLAN has neither,
    # so the honest answer here is a refusal rather than a flag nobody can satisfy.
    if "custom_scene" in data or "source" in (data.get("params") or {}):
        errs.append(
            f"{where}: custom Manim source is refused — a math scene authors a "
            f"template or a typed scene_program, never Python"
        )

    formulas = data.get("formulas") or []
    if not isinstance(formulas, list) or not all(
        isinstance(f, dict) and isinstance(f.get("latex"), str) and f["latex"].strip()
        for f in formulas
    ):
        errs.append(
            f"{where}: data.formulas must be a list of "
            f"{{latex, says}} objects — the ledger every displayed formula traces to"
        )
        formulas = []
    if len(formulas) < tpl.min_formulas:
        errs.append(
            f"{where}: template {tpl.id!r} needs at least {tpl.min_formulas} "
            f"entr{'y' if tpl.min_formulas == 1 else 'ies'} in data.formulas, "
            f"got {len(formulas)}"
        )

    params = data.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return errs + [f"{where}: data.params must be an object"]

    known = {p.name for p in tpl.params}
    for extra in sorted(set(params) - known):
        errs.append(
            f"{where}.params.{extra}: not a parameter of {tpl.id!r} "
            f"(it has {sorted(known)}) — an authored field with no consumer is inert"
        )
    for p in tpl.params:
        if p.name not in params:
            if p.required:
                errs.append(f"{where}.params.{p.name}: required by {tpl.id!r} ({p.doc})")
            continue
        errs.extend(_validate_param(p, params[p.name], len(formulas), where))

    errs.extend(_validate_roles(tpl, params, formulas, where))
    if tpl.id == "scene_program":
        errs.extend(_validate_scene_program(params.get("program"), where))
    if tpl.id == "concept_comparison" and not errs:
        if params.get("left") == params.get("right"):
            errs.append(f"{where}.params: a comparison needs two DISTINCT formulas")
    if tpl.id == "equation_sequence" and not errs:
        steps = params.get("steps") or []
        if len(steps) != len(set(steps)):
            errs.append(
                f"{where}.params.steps: a derivation cannot repeat a formula — "
                f"got {steps}"
            )
        at = params.get("at") or []
        if at and len(at) != len(steps) - 1:
            errs.append(
                f"{where}.params.at: give one spoken phrase per step AFTER the "
                f"first ({len(steps) - 1} needed), or omit it entirely — got {len(at)}"
            )
    return errs


def _validate_roles(
    tpl: MathTemplate, params: Dict[str, Any], formulas: List[Any], where: str
) -> List[str]:
    errs: List[str] = []
    roles = params.get("part_roles")
    if isinstance(roles, list):
        for role in roles:
            if role not in SEMANTIC_ROLES:
                errs.append(
                    f"{where}.params.part_roles: {role!r} is not a semantic role "
                    f"{sorted(SEMANTIC_ROLES)}"
                )
    role = params.get("role")
    if isinstance(role, str) and role not in SEMANTIC_ROLES:
        errs.append(
            f"{where}.params.role: {role!r} is not a semantic role "
            f"{sorted(SEMANTIC_ROLES)}"
        )
    return errs


def _validate_scene_program(program: Any, where: str) -> List[str]:
    """Round-trip a bespoke program through the ENGINE's own contract.

    Re-implementing SceneProgram validation here would be a second dialect for
    one decision. The engine's pydantic model rejects unknown fields, unresolved
    object ids, unsafe coordinate expressions and overlapping cues; borrowing it
    means the gate refuses exactly what the compiler would.
    """

    if not isinstance(program, dict):
        return [f"{where}.params.program: must be a SceneProgram object"]
    try:
        from math_animation.contracts import SceneProgram
    except ModuleNotFoundError:  # bare bridge without the engine installed
        return []
    try:
        SceneProgram.model_validate(program)
    except Exception as exc:  # pydantic ValidationError, or a contract ValueError
        detail = str(exc).replace("\n", " ")[:600]
        return [f"{where}.params.program: invalid SceneProgram — {detail}"]
    return []
