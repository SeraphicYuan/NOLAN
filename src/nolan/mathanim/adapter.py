"""A `math` scene -> the engine's `ProjectSpec`. The whole NOLAN/Manim seam.

Everything about timing stays NOLAN's:

  * `scene.dur` becomes `beat.duration_seconds`, and the engine's compiler pads
    the Manim scene to EXACTLY that (`self.wait(duration - cursor)`) and REFUSES
    to compile when the animation needs more time than the narration allows
    (`compiler.py` / `scene_compiler.py`). The clip is frame-exact by
    construction — narration owns duration, with no negotiation.
  * An `at` phrase is located by `nolan.hyperframes.sync._phrase_time`, THE
    phrase matcher for this repo, and handed over as clip-local seconds. The
    engine has its own `WordAnchor` path; using it would mean two matchers for
    one question ("when is this said?"), which is how they drift.
  * Manim never sees the audio, never mixes, never decides a duration. The
    engine's own FFmpeg composer stays dead code — `assemble-index` composes.

Reveals are SPREAD across the beat, never front-loaded. This is the math
analogue of `compose.py`'s shared reveal scheduler and exists for the same
reason (docs/WIRING_CHECKLIST.md #9): a derivation that writes three steps in
2.4s and then holds a frozen frame for 6.6s reads as a static slide, and the
steps pop before the voice reaches them.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from nolan.mathanim import registry, style as _style

# A beat id must satisfy the engine's `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Fractions of the beat reserved before the first reveal and after the last, so a
# math scene breathes at the cut instead of starting mid-animation.
LEAD_FRACTION = 0.06
TAIL_FRACTION = 0.18


class MathAuthoringError(ValueError):
    """The scene cannot be built. Message names the scene and the fix."""


def beat_id(frame_id: str, scene_id: str) -> str:
    raw = f"{frame_id}.{scene_id}".strip(".")
    safe = _ID_SAFE.sub("-", raw).strip("-.") or "math"
    if not safe[0].isalnum():
        safe = f"m{safe}"
    return safe[:128]


# --- timing ----------------------------------------------------------------------------------


def slice_words(
    words: Sequence[Dict[str, Any]], start: float, dur: float
) -> List[Dict[str, float]]:
    """The narration inside this scene's window, shifted to clip-local time.

    Section-relative in, clip-local out. Clipped rather than dropped at the edges
    so a word straddling the cut still anchors — the visual belongs to the words
    the viewer hears over it.
    """

    out: List[Dict[str, float]] = []
    end = start + dur
    for w in words or []:
        try:
            ws, we = float(w.get("start", 0)), float(w.get("end", 0))
        except (TypeError, ValueError):
            continue
        if we <= start or ws >= end or we <= ws:
            continue
        token = str(w.get("word") or w.get("text") or "").strip()
        if not token:
            continue
        out.append(
            {
                "word": token,
                "start_seconds": round(max(0.0, ws - start), 4),
                "end_seconds": round(min(dur, we - start), 4),
            }
        )
    # the engine rejects out-of-order or zero-length words; a clip can produce
    # both at a boundary, so drop rather than smuggle a degenerate entry through
    cleaned: List[Dict[str, float]] = []
    previous_end = -1.0
    for item in out:
        if item["end_seconds"] <= item["start_seconds"]:
            continue
        if item["start_seconds"] < previous_end:
            item["start_seconds"] = previous_end
            if item["end_seconds"] <= item["start_seconds"]:
                continue
        cleaned.append(item)
        previous_end = item["end_seconds"]
    return cleaned


def phrase_seconds(
    phrase: str, words: Sequence[Dict[str, Any]], start: float, dur: float
) -> Optional[float]:
    """Clip-local seconds where `phrase` is spoken, or None if it is not said.

    Delegates to `nolan.hyperframes.sync._phrase_time` — the repo's one phrase
    matcher, which already handles hyphenation, possessives and the
    spelled-out-vs-digits number problem ('nine hundred' vs Whisper's '900').
    """

    if not phrase or not words:
        return None
    try:
        from nolan.aligner import WordTimestamp
        from nolan.hyperframes.sync import _phrase_time
    except ImportError:  # pragma: no cover - bare env without the HF package
        return None
    # `_phrase_time` -> `flatten_words` wants WordTimestamp objects, not the raw
    # audio_meta dicts; sync.py does the same conversion at its two call sites.
    stream = [
        WordTimestamp(
            word=str(w.get("word") or w.get("text") or ""),
            start=float(w.get("start", 0)),
            end=float(w.get("end", 0)),
        )
        for w in words
        if (w.get("word") or w.get("text"))
    ]
    at = _phrase_time(str(phrase), stream, after=max(0.0, start - 0.75))
    if at is None:
        return None
    local = at - start
    if local < -0.5 or local > dur:
        return None
    return max(0.0, min(dur, local))


def spread(count: int, duration: float) -> List[float]:
    """`count` reveal times spread across the beat's usable window.

    The math counterpart of `compose._reveal_times`. Front-loading is impossible
    by construction: the last reveal lands at the end of the window, not at
    `lead + n*step` wherever that happens to fall.
    """

    if count <= 0:
        return []
    lead = duration * LEAD_FRACTION
    usable = max(0.0, duration * (1.0 - LEAD_FRACTION - TAIL_FRACTION))
    if count == 1:
        return [round(lead, 3)]
    step = usable / (count - 1)
    return [round(lead + i * step, 3) for i in range(count)]


def _cue_times(
    phrases: Sequence[str],
    count: int,
    duration: float,
    words: Sequence[Dict[str, Any]],
    start: float,
    where: str,
) -> Tuple[List[float], List[str]]:
    """Reveal times for `count` elements, honouring authored `at` phrases.

    An unmatched phrase falls back to its spread position and is REPORTED — a
    silently ignored anchor is the authored-but-unconsumed class, and the author
    would go on believing they timed that step.
    """

    times = spread(count, duration)
    notes: List[str] = []
    for index, phrase in enumerate(phrases[:count]):
        if not phrase:
            continue
        at = phrase_seconds(phrase, words, start, duration)
        if at is None:
            notes.append(
                f"{where}: the phrase {phrase!r} is not spoken inside this scene's "
                f"window — step {index + 1} falls back to its spread position; "
                f"anchor it to words the narration actually says here"
            )
            continue
        times[index] = round(at, 3)
    # monotonic: the engine refuses a cue that starts before the previous ends,
    # and an author anchoring step 3 earlier than step 2 has made an ordering
    # mistake worth naming rather than a timeline worth silently reshuffling
    for i in range(1, len(times)):
        if times[i] < times[i - 1]:
            notes.append(
                f"{where}: reveal {i + 1} is anchored at {times[i]:.2f}s, before "
                f"reveal {i} at {times[i - 1]:.2f}s — the steps are out of order"
            )
            times[i] = times[i - 1]
    return times, notes


# --- the ledger ------------------------------------------------------------------------------


def _ledger(formulas: Sequence[Dict[str, Any]], where: str):
    from math_animation.contracts import FormulaSpec, MathClaim, MathLedger

    specs, claims = [], []
    for index, item in enumerate(formulas):
        fid = f"f{index:02d}"
        latex = str(item["latex"]).strip()
        says = str(item.get("says") or "").strip()
        specs.append(
            FormulaSpec(
                id=fid,
                latex_parts=[latex],
                plain_language=says or f"the expression {latex}",
                symbol_roles=item.get("symbols") or {},
            )
        )
        # An authored citation makes the claim VERIFIED with its evidence; without
        # one it is ASSUMED and says so. Never `needs_review` by default: that is
        # the engine's "nobody has looked at this" state, and an author who typed
        # the formula has looked at it. What must not happen is a model-invented
        # equation passing as fact, which is what the ledger + gate prevent.
        citation = str(item.get("verified") or "").strip()
        claims.append(
            MathClaim(
                id=f"c{index:02d}",
                statement=says or f"The scene asserts {latex}.",
                verification="verified" if citation else "assumed",
                evidence=[citation] if citation else [f"authored in {where}"],
            )
        )
    return MathLedger(claims=claims, formulas=specs), [s.id for s in specs]


# --- templates -------------------------------------------------------------------------------


def _blocks_for(
    name: str,
    params: Dict[str, Any],
    latex: List[str],
    ids: List[str],
    duration: float,
    words,
    start: float,
    where: str,
    style_payload: Dict[str, Any],
) -> Tuple[list, List[str]]:
    """The six single-block templates. Returns (blocks, notes)."""

    from math_animation.contracts import (
        EquationRevealBlock,
        EquationTransformBlock,
        FunctionPlotBlock,
        NumberLineBlock,
        SecantToTangentBlock,
        TitleCardBlock,
    )

    notes: List[str] = []
    # One block owns the whole beat, so give it a run_time proportional to the window instead of the
    # engine's 1.0s default followed by a long frozen hold. `hold_seconds` is filled in by
    # `_fit_block`, which MEASURES the compiled block rather than assuming its length is
    # run_time + hold: a multi-animation block (function_plot draws axes AND then the curve) is
    # longer than its nominal run_time, and assuming otherwise overran the window by 0.35s.
    run_time = max(0.6, min(3.0, duration * 0.45))
    at, notes_at = _cue_times([str(params.get("at") or "")], 1, duration, words, start, where)
    notes.extend(notes_at)
    lead = at[0]
    common = {"run_time": run_time, "hold_seconds": 0.0}
    if lead > 0.01:
        from math_animation.contracts import SecondsAnchor

        common["start_at"] = SecondsAnchor(seconds=round(lead, 3), scope="beat")

    if name == "title_card":
        block = (
            TitleCardBlock(
                id="title",
                title=str(params["title"]),
                subtitle=(str(params["subtitle"]) if params.get("subtitle") else None),
                **common,
            )
        )
    elif name == "equation_reveal":
        index = int(params["formula"])
        block = (
            EquationRevealBlock(
                id="reveal",
                formula_id=ids[index],
                latex_parts=[latex[index]],
                part_roles=list(params.get("part_roles") or []),
                caption=(str(params["caption"]) if params.get("caption") else None),
                **common,
            )
        )
    elif name == "equation_transform":
        block = (
            EquationTransformBlock(
                id="transform",
                from_latex=[latex[int(params["from"])]],
                to_latex=[latex[int(params["to"])]],
                caption=(str(params["caption"]) if params.get("caption") else None),
                **common,
            )
        )
    elif name == "function_plot":
        label_index = params.get("label")
        block = (
            FunctionPlotBlock(
                id="plot",
                expression=str(params["expression"]),
                label_latex=(
                    latex[int(label_index)] if isinstance(label_index, int) else None
                ),
                role=str(params.get("role") or "primary"),
                **_ranges(params, x=(-4.0, 4.0, 1.0), y=(-3.0, 5.0, 1.0)),
                **common,
            )
        )
    elif name == "number_line":
        block = (
            NumberLineBlock(
                id="line",
                values=[float(v) for v in params["values"]],
                labels=[str(v) for v in (params.get("labels") or [])],
                role=str(params.get("role") or "primary"),
                **_ranges(params, x=(-5.0, 5.0, 1.0)),
                **common,
            )
        )
    elif name == "secant_to_tangent":
        optional = {
            key: float(params[key])
            for key in ("x0", "h_start", "h_end")
            if params.get(key) is not None
        }
        block = (
            SecantToTangentBlock(
                id="secant",
                expression=str(params["expression"]),
                caption=(str(params["caption"]) if params.get("caption") else None),
                **_ranges(params, x=(-4.0, 4.0, 1.0), y=(-2.0, 5.0, 1.0)),
                **optional,
                **common,
            )
        )
    else:
        raise MathAuthoringError(f"{where}: {name!r} is not a block template")
    return [_fit_block(block, style_payload, lead, duration, where)], notes


def _fit_block(block, style_payload, lead: float, duration: float, where: str):
    """Set a block's hold so the beat ends exactly on time — by MEASURING it, not assuming.

    A block's real length is whatever its emitter produces: `function_plot` draws the axes and THEN
    the curve, so it runs longer than its nominal `run_time`. Computing the hold as
    `duration - run_time - lead` overran a 6.0s window by 0.35s and the compiler (correctly) refused
    the whole render. Compile it once, read the number back, and fill the remainder.
    """

    from math_animation.blocks import compile_block
    from math_animation.contracts import StyleTemplateRef
    from math_animation.style import normalize_style

    style = normalize_style(StyleTemplateRef(raw=style_payload))
    measured = compile_block(block, style).duration_seconds
    remaining = duration - lead - measured
    if remaining < -1e-6:
        raise MathAuthoringError(
            f"{where}: this template needs {lead + measured:.2f}s but the narration window is "
            f"{duration:.2f}s. Narration owns duration — give the scene more of the beat, or use a "
            f"template with less to draw."
        )
    return block.model_copy(update={"hold_seconds": round(max(0.0, remaining), 3)})


def _ranges(params: Dict[str, Any], *, x=None, y=None) -> Dict[str, tuple]:
    out: Dict[str, tuple] = {}
    if x is not None:
        out["x_range"] = tuple(float(v) for v in (params.get("x_range") or x))
    if y is not None:
        out["y_range"] = tuple(float(v) for v in (params.get("y_range") or y))
    return out


def _scene_program_for(
    name: str,
    params: Dict[str, Any],
    latex: List[str],
    ids: List[str],
    duration: float,
    words,
    start: float,
    where: str,
):
    """The two pedagogy templates + the bespoke passthrough."""

    from math_animation.contracts import SceneProgram, SecondsAnchor
    from math_animation.expanded_planning import (
        ConceptComparisonPlan,
        EquationSequencePlan,
        scene_for_comparison,
        scene_for_sequence,
    )

    notes: List[str] = []
    if name == "scene_program":
        # Already typed and already validated by the registry. Passed through
        # untouched: the author authored a program, not a hint.
        return SceneProgram.model_validate(params["program"]), notes

    if name == "equation_sequence":
        steps = [int(i) for i in params["steps"]]
        program = scene_for_sequence(
            beat_id="seq",
            duration=duration,
            plan=EquationSequencePlan(formula_indices=steps),
            formulas=latex,
            formula_ids=ids,
        )
        # scene_for_sequence emits cues back to back from t=0 — correct for the
        # engine's standalone pacing, front-loaded inside a NOLAN beat. Re-anchor
        # each cue on its spread (or authored) time so the derivation develops
        # across the whole window.
        phrases = [""] + [str(p) for p in (params.get("at") or [])]
        times, at_notes = _cue_times(
            phrases, len(program.cues), duration, words, start, where
        )
        notes.extend(at_notes)
        program = _reanchor(program, times, duration, where, notes)
        return program, notes

    if name == "concept_comparison":
        program = scene_for_comparison(
            beat_id="cmp",
            duration=duration,
            plan=ConceptComparisonPlan(
                left_formula_index=int(params["left"]),
                right_formula_index=int(params["right"]),
                left_label=params.get("left_label"),
                right_label=params.get("right_label"),
            ),
            formulas=latex,
            formula_ids=ids,
        )
        program = _reanchor(program, spread(len(program.cues), duration), duration, where, notes)
        return program, notes

    raise MathAuthoringError(f"{where}: {name!r} is not a scene-program template")


def _reanchor(program, times: List[float], duration: float, where: str, notes: List[str]):
    """Give each cue an explicit start, keeping the sequence legal.

    The engine refuses a cue that begins before the previous one ends, so a time
    that would overlap is pushed to the earliest legal moment and reported. The
    alternative — letting the compile fail — spends the author's attention on a
    stack trace instead of on the sentence that says what to fix.
    """

    from math_animation.contracts import SecondsAnchor

    cues = list(program.cues)
    cursor = 0.0
    for index, cue in enumerate(cues):
        wanted = times[index] if index < len(times) else cursor
        if wanted < cursor:
            if index:
                notes.append(
                    f"{where}: reveal {index + 1} wanted {wanted:.2f}s but the "
                    f"previous step is still animating until {cursor:.2f}s — "
                    f"moved to {cursor:.2f}s; give the beat more room or fewer steps"
                )
            wanted = cursor
        cues[index] = cue.model_copy(
            update={"start_at": SecondsAnchor(seconds=round(wanted, 3), scope="beat")}
        )
        cursor = wanted + cue.duration_seconds
    if cursor > duration + 1e-6:
        raise MathAuthoringError(
            f"{where}: the animation needs {cursor:.2f}s but the narration window "
            f"is {duration:.2f}s. Narration owns duration — shorten the template "
            f"(fewer steps) or give the scene more of the beat."
        )
    return program.model_copy(update={"cues": cues})


# --- the public builder ----------------------------------------------------------------------


def project_from_scene(
    scene: Dict[str, Any],
    *,
    frame_id: str,
    theme: Optional[str],
    canvas: Dict[str, Any],
    words: Sequence[Dict[str, Any]] = (),
) -> Tuple[Any, List[str]]:
    """Build the one-beat `ProjectSpec` for a `math` scene. Returns (project, notes).

    `notes` are authoring advisories that did NOT stop the build (an unmatched
    `at` phrase, a reveal nudged to stay legal). The resolver surfaces them; they
    are not swallowed.
    """

    from math_animation.contracts import (
        BeatSpec,
        NarrationInput,
        ProjectSpec,
        RenderSettings,
        RequestSpec,
        StyleTemplateRef,
        UtteranceTiming,
        WordTiming,
    )

    scene_id = str(scene.get("id") or "s")
    where = f"{frame_id}/{scene_id}"
    data = scene.get("data") or {}

    errors = registry.validate_scene_data(data, where)
    if errors:
        raise MathAuthoringError("; ".join(errors))

    duration = float(scene.get("dur") or 0)
    if duration <= 0:
        raise MathAuthoringError(f"{where}: a math scene needs a positive dur")
    start = float(scene.get("start") or 0)

    name = str(data["template"])
    params = dict(data.get("params") or {})
    raw_formulas = list(data.get("formulas") or [])
    ledger, ids = _ledger(raw_formulas, where)
    latex = [str(f["latex"]).strip() for f in raw_formulas]

    local_words = slice_words(words, start, duration)
    utterance_id = f"vo-{beat_id(frame_id, scene_id)}"[:128]
    narration = NarrationInput(
        provider="nolan",
        utterances=[
            UtteranceTiming(
                id=utterance_id,
                text=" ".join(w["word"] for w in local_words),
                words=[
                    WordTiming(
                        word=w["word"],
                        start_seconds=w["start_seconds"],
                        end_seconds=w["end_seconds"],
                    )
                    for w in local_words
                ],
            )
        ]
        if local_words
        else [],
    )

    # The style payload is resolved BEFORE the visuals are built: `_fit_block` compiles a block once
    # to measure its real length, and the emitters need the style tokens to do that.
    height = int(canvas.get("height") or 1080)
    payload = _style.style_payload(theme, canvas_height=height)

    notes: List[str] = []
    blocks, program = [], None
    if name in {"equation_sequence", "concept_comparison", "scene_program"}:
        program, notes = _scene_program_for(
            name, params, latex, ids, duration, words, start, where
        )
    else:
        blocks, notes = _blocks_for(
            name, params, latex, ids, duration, words, start, where, payload
        )

    # Deliberately NOT falling back to `kicker`. It is design copy ("STEP TWO") — `block_registry`
    # classifies it as intent rather than content — and, more practically, everything that reaches
    # the ProjectSpec is part of the clip's cache key. Letting chrome in would make a caption typo
    # cost a full Manim re-render, which is what the HTML chrome layer exists to avoid.
    title = str(data.get("title") or data.get("objective") or name.replace("_", " "))
    objective = str(data.get("objective") or title)
    beat = BeatSpec(
        id=beat_id(frame_id, scene_id),
        title=title[:120],
        learning_objective=objective[:400],
        narration_utterance_id=utterance_id if local_words else None,
        duration_seconds=duration,
        blocks=blocks,
        scene_program=program,
    )

    notes.extend(_style.check_roles(payload, used_roles=_roles_used(params)))

    project = ProjectSpec(
        project_id=beat_id(frame_id, scene_id),
        title=title[:120],
        request=RequestSpec(
            source_kind="screenplay",
            content=objective,
            script_policy="locked",  # NOLAN's script is already written and spoken
            target_duration_seconds=duration,
        ),
        math_ledger=ledger,
        narration=narration,
        style=StyleTemplateRef(
            template_id=_safe_template_id(theme),
            version="nolan-theme-v1",
            provider="nolan",
            raw=payload,
        ),
        beats=[beat],
        render=RenderSettings(
            renderer="cairo",
            quality="h",
            pixel_width=int(canvas.get("width") or 1920),
            pixel_height=height,
            frame_rate=int(canvas.get("fps") or 30),
            transparent=False,  # full-frame ground; the frame paints chrome over it
        ),
    )
    return project, notes


def _roles_used(params: Dict[str, Any]) -> List[str]:
    used = [r for r in (params.get("part_roles") or []) if isinstance(r, str)]
    if isinstance(params.get("role"), str):
        used.append(params["role"])
    return used


def _safe_template_id(theme: Optional[str]) -> str:
    safe = _ID_SAFE.sub("-", str(theme or "default")).strip("-.")
    return safe[:128] if safe and safe[0].isalnum() else "default"
