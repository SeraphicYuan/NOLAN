"""Conservative deterministic script drafting used for plumbing and prototypes."""

from __future__ import annotations

import re

from math_animation.contracts import (
    BeatSpec,
    EquationRevealBlock,
    NarrationInput,
    ProjectSpec,
    RequestSpec,
    StyleTemplateRef,
    TitleCardBlock,
    UtteranceTiming,
)

_INLINE_MATH = re.compile(r"\$(.+?)\$", flags=re.DOTALL)
_DISPLAY_MATH = re.compile(r"\\\[(.+?)\\\]", flags=re.DOTALL)


def _paragraphs(script: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", script) if part.strip()]
    return parts or [script.strip()]


def _short_title(text: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return sentence if len(sentence) <= 72 else sentence[:69].rstrip() + "..."


def draft_from_script(
    script: str,
    *,
    project_id: str,
    title: str,
    audience: str = "general",
    style: StyleTemplateRef | None = None,
) -> ProjectSpec:
    """Create a reviewable project without claiming to solve pedagogy automatically.

    This fallback is intentionally simple. A future agent planner should produce
    the exact same ``ProjectSpec`` contract.
    """

    beats: list[BeatSpec] = []
    utterances: list[UtteranceTiming] = []
    for index, paragraph in enumerate(_paragraphs(script), start=1):
        beat_id = f"beat-{index:03d}"
        utterance_id = f"utterance-{index:03d}"
        utterances.append(
            UtteranceTiming(id=utterance_id, text=paragraph, words=[])
        )
        duration = max(3.0, len(paragraph.split()) / 2.35 + 0.5)
        formulas = _INLINE_MATH.findall(paragraph) + _DISPLAY_MATH.findall(paragraph)
        if formulas:
            base = 1.6
            block = EquationRevealBlock(
                id=f"{beat_id}.equation",
                latex_parts=formulas,
                caption=_short_title(_INLINE_MATH.sub("", paragraph).strip()),
                run_time=1.0,
                hold_seconds=max(0.0, duration - base),
            )
        else:
            base = 1.35
            block = TitleCardBlock(
                id=f"{beat_id}.title",
                title=_short_title(paragraph),
                run_time=1.0,
                hold_seconds=max(0.0, duration - base),
            )
        beats.append(
            BeatSpec(
                id=beat_id,
                title=_short_title(paragraph),
                learning_objective="Preserve this script beat for visual review.",
                narration_utterance_id=utterance_id,
                duration_seconds=duration,
                blocks=[block],
            )
        )
    return ProjectSpec(
        project_id=project_id,
        title=title,
        request=RequestSpec(
            source_kind="script",
            content=script,
            audience=audience,
            script_policy="review",
            target_duration_seconds=sum(
                beat.duration_seconds or 0.0 for beat in beats
            ),
        ),
        narration=NarrationInput(
            provider="external",
            utterances=utterances,
        ),
        style=style or StyleTemplateRef(),
        beats=beats,
    )
