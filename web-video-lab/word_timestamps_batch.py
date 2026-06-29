"""Batch word timestamps for several wavs (loads whisper once). CPU.
Usage: python word_timestamps_batch.py out.json wav1 wav2 ...
"""
from __future__ import annotations
import json, sys
from pathlib import Path


def main() -> None:
    out = Path(sys.argv[1])
    wavs = sys.argv[2:]
    from nolan.whisper import WhisperTranscriber, WhisperConfig
    tr = WhisperTranscriber(WhisperConfig(model_size="base", device="cpu", compute_type="int8"))
    res = {}
    for w in wavs:
        words = tr.transcribe_words(Path(w))
        res[Path(w).stem] = [{"word": x.word, "start": round(x.start, 3), "end": round(x.end, 3)} for x in words]
        print(Path(w).stem, len(res[Path(w).stem]), "words")
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
