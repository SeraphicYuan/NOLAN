"""Lab probe: per-word timestamps from an OmniVoice wav via NOLAN's whisper
(read-only). The motion-driving input for the compute-don't-capture approach.

Usage: python word_timestamps.py <audio.wav> [out.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    wav = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    from nolan.whisper import WhisperTranscriber, WhisperConfig

    # CPU avoids a missing-cuBLAS issue in this env; fine for short clips.
    tr = WhisperTranscriber(WhisperConfig(model_size="base", device="cpu", compute_type="int8"))
    words = tr.transcribe_words(wav)
    data = [{"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3),
             "p": round(w.probability, 3)} for w in words]
    for w in data:
        print(f"  {w['start']:6.2f}–{w['end']:6.2f}  {w['word']}")
    print(f"{len(data)} words")
    if out:
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"-> {out}")


if __name__ == "__main__":
    main()
