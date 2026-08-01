"""Resolve Nolan word timings and beat-relative anchors into deterministic times."""

from __future__ import annotations

from dataclasses import dataclass

from math_animation.contracts import (
    BeatFractionAnchor,
    BeatSpec,
    ProjectSpec,
    SecondsAnchor,
    TimelineAnchor,
    UtteranceTiming,
    WordAnchor,
)


@dataclass(frozen=True)
class ResolvedBeat:
    beat: BeatSpec
    start_seconds: float
    duration_seconds: float
    utterance: UtteranceTiming | None

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


def _estimated_utterance_duration(utterance: UtteranceTiming) -> float:
    # Conservative drafting estimate only; Nolan word timestamps supersede it.
    return max(2.0, len(utterance.text.split()) / 2.35 + 0.5)


def _estimated_scene_program_duration(beat: BeatSpec, beat_start: float) -> float:
    assert beat.scene_program is not None
    cursor = 0.0
    for cue in beat.scene_program.cues:
        if cue.start_at is None:
            start = cursor
        elif isinstance(cue.start_at, SecondsAnchor):
            start = (
                cue.start_at.seconds
                if cue.start_at.scope == "beat"
                else cue.start_at.seconds - beat_start
            )
        else:
            raise ValueError(
                f"beat {beat.id!r} needs duration_seconds when its scene program "
                "uses word or beat-fraction anchors"
            )
        if start < cursor - 1e-6:
            raise ValueError(
                f"scene cue {cue.id!r} overlaps the preceding cue; use a "
                "parallel cue for simultaneous actions"
            )
        cursor = start + cue.duration_seconds
    return cursor


def resolve_beats(project: ProjectSpec) -> list[ResolvedBeat]:
    utterances = {item.id: item for item in project.narration.utterances}
    resolved: list[ResolvedBeat] = []
    cursor = 0.0

    for beat in project.beats:
        utterance = (
            utterances.get(beat.narration_utterance_id)
            if beat.narration_utterance_id
            else None
        )
        aligned_start: float | None = None
        aligned_duration: float | None = None
        if utterance and utterance.words:
            aligned_start = utterance.words[0].start_seconds
            aligned_duration = utterance.words[-1].end_seconds - aligned_start

        start = aligned_start if aligned_start is not None else cursor
        if start < cursor - 1e-6:
            raise ValueError(
                f"beat {beat.id!r} overlaps the preceding beat according to "
                "narration word timestamps"
            )
        if beat.duration_seconds is not None:
            duration = beat.duration_seconds
            if aligned_duration is not None and duration + 1e-6 < aligned_duration:
                raise ValueError(
                    f"beat {beat.id!r} duration is shorter than its aligned narration"
                )
        elif aligned_duration is not None:
            duration = aligned_duration
        elif utterance is not None:
            duration = _estimated_utterance_duration(utterance)
        elif beat.scene_program is not None:
            duration = _estimated_scene_program_duration(beat, start)
        else:
            duration = sum(
                block.run_time + block.hold_seconds for block in beat.blocks
            )

        item = ResolvedBeat(
            beat=beat,
            start_seconds=start,
            duration_seconds=duration,
            utterance=utterance,
        )
        resolved.append(item)
        cursor = item.end_seconds
    return resolved


def resolve_anchor(anchor: TimelineAnchor, beat: ResolvedBeat) -> float:
    """Return an anchor as seconds from the start of the rendered beat clip."""

    if isinstance(anchor, BeatFractionAnchor):
        return beat.duration_seconds * anchor.fraction
    if isinstance(anchor, SecondsAnchor):
        if anchor.scope == "beat":
            return anchor.seconds
        return anchor.seconds - beat.start_seconds
    if isinstance(anchor, WordAnchor):
        if beat.utterance is None:
            raise ValueError(
                f"word anchor references {anchor.utterance_id!r}, but beat "
                f"{beat.beat.id!r} has no narration utterance"
            )
        if beat.utterance.id != anchor.utterance_id:
            raise ValueError(
                f"word anchor for {anchor.utterance_id!r} cannot be resolved in "
                f"beat {beat.beat.id!r} ({beat.utterance.id!r})"
            )
        try:
            word = beat.utterance.words[anchor.word_index]
        except IndexError as exc:
            raise ValueError(
                f"word index {anchor.word_index} is outside utterance "
                f"{anchor.utterance_id!r}"
            ) from exc
        absolute = (
            word.start_seconds if anchor.edge == "start" else word.end_seconds
        ) + anchor.offset_seconds
        narration_origin = (
            beat.utterance.words[0].start_seconds
            if beat.utterance.words
            else beat.start_seconds
        )
        return absolute - narration_origin
    raise TypeError(f"unsupported timeline anchor: {type(anchor).__name__}")
