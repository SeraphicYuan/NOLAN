"""Synthetic Nolan-like narration fixtures for integration testing."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from math_animation.contracts import NarrationInput, UtteranceTiming, WordTiming


def generate_synthetic_narration(
    utterances: list[tuple[str, str]],
    output_path: Path,
    *,
    sample_rate: int = 24_000,
    word_seconds: float = 0.34,
    word_gap_seconds: float = 0.07,
    utterance_gap_seconds: float = 0.45,
    trailing_silence_seconds: float = 0.5,
) -> NarrationInput:
    """Create deterministic tone audio with exact word-level timestamps.

    This is deliberately not fake speech. Each word receives a short,
    frequency-coded tone followed by silence, which makes sync errors audible
    and measurable without depending on a TTS provider.
    """

    if not utterances:
        raise ValueError("at least one utterance is required")
    if sample_rate < 8_000:
        raise ValueError("sample_rate must be at least 8000")
    if (
        word_seconds <= 0
        or word_gap_seconds < 0
        or utterance_gap_seconds < 0
        or trailing_silence_seconds < 0
    ):
        raise ValueError("synthetic narration durations must be non-negative")

    samples: list[int] = []
    timings: list[UtteranceTiming] = []

    def append_silence(seconds: float) -> None:
        samples.extend([0] * round(seconds * sample_rate))

    for utterance_index, (utterance_id, text) in enumerate(utterances):
        words = text.split()
        if not words:
            raise ValueError(f"utterance {utterance_id!r} has no words")
        word_timings: list[WordTiming] = []
        for word_index, word in enumerate(words):
            start = len(samples) / sample_rate
            frequency = 330 + 23 * ((utterance_index * 7 + word_index) % 12)
            frame_count = round(word_seconds * sample_rate)
            for frame in range(frame_count):
                envelope = min(
                    1.0,
                    frame / max(1, round(0.02 * sample_rate)),
                    (frame_count - frame) / max(1, round(0.03 * sample_rate)),
                )
                value = int(
                    0.22
                    * 32767
                    * max(0.0, envelope)
                    * math.sin(2 * math.pi * frequency * frame / sample_rate)
                )
                samples.append(value)
            end = len(samples) / sample_rate
            word_timings.append(
                WordTiming(
                    word=word,
                    start_seconds=start,
                    end_seconds=end,
                )
            )
            if word_index < len(words) - 1:
                append_silence(word_gap_seconds)
        timings.append(
            UtteranceTiming(
                id=utterance_id,
                text=text,
                words=word_timings,
            )
        )
        if utterance_index < len(utterances) - 1:
            append_silence(utterance_gap_seconds)

    append_silence(trailing_silence_seconds)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(
            b"".join(struct.pack("<h", sample) for sample in samples)
        )
    return NarrationInput(
        provider="external",
        audio_path=str(output_path),
        utterances=timings,
    )
