from __future__ import annotations

import pytest
from pydantic import ValidationError

from math_animation.contracts import (
    NarrationInput,
    UtteranceTiming,
    WordTiming,
)
from math_animation.adapters.nolan import NolanAlignmentAdapter


def test_word_timings_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="ordered and non-overlapping"):
        UtteranceTiming(
            id="u1",
            text="two words",
            words=[
                WordTiming(word="two", start_seconds=1.0, end_seconds=2.0),
                WordTiming(word="words", start_seconds=1.5, end_seconds=2.5),
            ],
        )


def test_nolan_alignment_adapter_accepts_common_field_names() -> None:
    narration = NolanAlignmentAdapter.from_mapping(
        {
            "audio_path": "voice.wav",
            "segments": [
                {
                    "segment_id": "u1",
                    "transcript": "A derivative is a slope.",
                    "tokens": [
                        {"token": "A", "start": 0.0, "end": 0.2},
                        {"token": "derivative", "start": 0.2, "end": 0.8},
                    ],
                }
            ],
        }
    )
    assert isinstance(narration, NarrationInput)
    assert narration.provider == "nolan"
    assert narration.utterances[0].words[1].word == "derivative"
