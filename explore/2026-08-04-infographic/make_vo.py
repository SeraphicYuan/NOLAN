"""Test D narration: synthesize the 10s script and recover REAL word timings.

The headline check for test D is "each subject's first visible frame lands within +/-150ms of its
noun". That is only meaningful against real narration — an estimate from words-per-minute would be
grading the harness against itself. So: clone a library voice, synthesize one section, run NOLAN's
own aligner over it, and write the noun times out.

    python -X utf8 explore/2026-08-04-infographic/make_vo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

OUT = HERE / "_testD"
VOICE = REPO / "voices" / "beat-the-noise-narrator"

SCRIPT = ("A data centre never arrives alone. It brings a power meter, a water line, "
          "a zoning fight — and a bet the chips will earn it all back.")

# The noun each collage subject must land on. Order is the entry order.
ANCHORS = [
    ("smart_meter_00", "meter"),
    ("water_glass_00", "water"),
    ("gavel_01", "zoning"),
    ("gpu_card_00", "chips"),
    ("cash_stack_00", "back"),
]


def main() -> int:
    from nolan.config import load_config
    from nolan.voice_pipeline import synthesize_sections
    from nolan import aligner

    work = OUT / "voice"
    work.mkdir(parents=True, exist_ok=True)
    meta = json.loads((VOICE / "meta.json").read_text(encoding="utf-8"))

    from nolan.tts import create_tts_provider

    cfg = load_config()
    provider = create_tts_provider(cfg.tts)
    made = synthesize_sections(
        provider, [SCRIPT], work,
        ref_audio=str(VOICE / "sample.wav"), ref_text=meta["ref_text"],
    )
    wav = Path(next(iter(made.values())))
    print(f"synthesized {wav.name}")

    words, _, _ = aligner.transcribe_and_align(wav, [], model_size="base", language="en")
    flat = aligner.flatten_words(words)
    print(f"aligned {len(flat)} tokens")

    # Resolve each anchor noun to its spoken time. Last occurrence wins for 'back' (it appears once,
    # but be explicit rather than lucky).
    times = {}
    for asset, noun in ANCHORS:
        hits = [(t, a, b) for (t, a, b) in flat if t.strip(".,;:—-").lower() == noun]
        if not hits:
            print(f"  UNMATCHED {noun!r} — the aligner did not hear it")
            continue
        times[asset] = {"noun": noun, "start": round(hits[0][1], 3), "end": round(hits[0][2], 3)}
        print(f"  {noun:8} -> {hits[0][1]:6.2f}s")

    import wave
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / float(w.getframerate())

    (OUT / "narration.json").write_text(json.dumps({
        "script": SCRIPT, "wav": str(wav), "duration_s": round(dur, 3),
        "words": [{"t": t, "start": round(a, 3), "end": round(b, 3)} for t, a, b in flat],
        "anchors": times,
    }, indent=1), encoding="utf-8")

    missing = [a for a, _ in ANCHORS if a not in times]
    print(f"\nduration {dur:.2f}s, {len(times)}/{len(ANCHORS)} anchors resolved")
    if missing:
        print(f"MISSING: {missing} — the anchor check cannot run for these")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
