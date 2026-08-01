"""Temporary tolerant adapters for Nolan timing and style payloads."""

from __future__ import annotations

from typing import Any

from math_animation.contracts import (
    NarrationInput,
    StyleTemplateRef,
    UtteranceTiming,
    WordTiming,
)


def _pick(payload: dict[str, Any], *names: str, required: bool = True) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    if required:
        raise ValueError(f"missing one of required keys: {', '.join(names)}")
    return None


class NolanAlignmentAdapter:
    """Accept a minimal family of common alignment spellings.

    This is deliberately isolated so Nolan's real schema can later be supported
    by changing only this adapter.
    """

    @staticmethod
    def from_mapping(payload: dict[str, Any]) -> NarrationInput:
        utterances: list[UtteranceTiming] = []
        for item in payload.get("utterances", payload.get("segments", [])):
            words = [
                WordTiming(
                    word=str(_pick(word, "word", "text", "token")),
                    start_seconds=float(
                        _pick(word, "start_seconds", "start", "start_time")
                    ),
                    end_seconds=float(
                        _pick(word, "end_seconds", "end", "end_time")
                    ),
                )
                for word in item.get("words", item.get("tokens", []))
            ]
            utterances.append(
                UtteranceTiming(
                    id=str(_pick(item, "id", "utterance_id", "segment_id")),
                    text=str(_pick(item, "text", "transcript")),
                    words=words,
                )
            )
        return NarrationInput(
            provider="nolan",
            audio_path=payload.get("audio_path"),
            utterances=utterances,
        )


class NolanStyleAdapter:
    @staticmethod
    def from_mapping(
        payload: dict[str, Any],
        *,
        template_id: str,
        version: str = "unknown",
    ) -> StyleTemplateRef:
        return StyleTemplateRef(
            template_id=template_id,
            version=version,
            provider="nolan",
            raw=payload,
        )
