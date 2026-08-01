from __future__ import annotations

import wave
from pathlib import Path

from math_animation.synthetic import generate_synthetic_narration


def test_synthetic_narration_has_exact_ordered_word_timing(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "narration.wav"
    narration = generate_synthetic_narration(
        [
            ("u1", "First visual now"),
            ("u2", "Second beat"),
        ],
        destination,
    )

    assert destination.is_file()
    assert narration.utterances[0].words[2].word == "now"
    assert (
        narration.utterances[1].words[0].start_seconds
        > narration.utterances[0].words[-1].end_seconds
    )
    with wave.open(str(destination), "rb") as audio:
        assert audio.getframerate() == 24_000
        assert audio.getnchannels() == 1
        assert audio.getnframes() > 0
