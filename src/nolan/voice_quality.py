"""VO quality scoring (P5.1) — the perceptual sensor the mechanical A2 gate lacks.

ASR round-trip: transcribe a synthesized beat with the same Whisper we run for captions,
token-normalize both the transcript and the *spoken* (number-normalized) script text, and
compute a per-beat word-error-rate. High WER ⇒ the TTS said the wrong thing (mispronounced a
name, garbled a number, dropped/added words) — exactly what the retake loop should target.

`word_error_rate` and `normalize_words` are pure + unit-tested; `score_voiceover` scores wavs
already on disk (no GPU — Whisper runs CPU/int8), so it validates an existing VO immediately.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Optional


def normalize_words(text: str) -> List[str]:
    """Tokens for WER: expand numbers the way TTS speaks them (A1), lowercase, drop
    punctuation. So the reference matches what the voice actually says ('1888' → eighteen
    eighty eight), not the written form."""
    from nolan.tts_normalize import normalize_for_speech
    t = normalize_for_speech(text or "").lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return t.split()


def word_error_rate(ref: List[str], hyp: List[str]) -> float:
    """Word-level Levenshtein distance / len(ref) — the standard WER. 0.0 = perfect."""
    if not ref:
        return 0.0 if not hyp else 1.0
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return round(prev[n] / m, 3)


def score_section(wav, text: str, *, transcribe: Callable[[object], str]) -> dict:
    """WER for one beat. ``transcribe(wav) -> str`` is injectable (a fake in tests, Whisper live)."""
    ref = normalize_words(text)
    hyp = normalize_words(transcribe(wav))
    return {"wer": word_error_rate(ref, hyp), "ref_words": len(ref), "hyp_words": len(hyp)}


def whisper_transcriber(model_size: str = "base") -> Callable[[object], str]:
    """A CPU Whisper transcriber (no GPU) → flat text, for scoring existing wavs."""
    from nolan.whisper import WhisperTranscriber, WhisperConfig
    tr = WhisperTranscriber(WhisperConfig(model_size=model_size, device="cpu",
                                          compute_type="int8"))
    return lambda wav: " ".join(w.word for w in tr.transcribe_words(Path(wav)))


def _body(s) -> str:
    return (s.get("body") if isinstance(s, dict) else str(s)) or ""


def score_voiceover(vo_dir, sections, *, transcribe: Optional[Callable] = None,
                    model_size: str = "base", wer_warn: float = 0.15) -> dict:
    """Score every beat of a VO on disk. Returns per-section WER + the flagged (high-WER) beats
    + mean WER. ``transcribe`` defaults to CPU Whisper; pass a fake in tests."""
    vo_dir = Path(vo_dir)
    tr = transcribe or whisper_transcriber(model_size)
    out = []
    for i, s in enumerate(sections):
        wav = vo_dir / "_work" / f"sec_{i:04d}.wav"
        if not wav.exists():
            out.append({"index": i, "present": False})
            continue
        sc = score_section(wav, _body(s), transcribe=tr)
        sc.update(index=i, present=True, flag=sc["wer"] > wer_warn)
        out.append(sc)
    scored = [s for s in out if s.get("present")]
    mean = round(sum(s["wer"] for s in scored) / len(scored), 3) if scored else None
    return {"sections": out, "flagged": [s["index"] for s in scored if s["flag"]],
            "mean_wer": mean, "wer_warn": wer_warn}
