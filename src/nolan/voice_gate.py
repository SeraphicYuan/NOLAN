"""Voiceover quality gate (A2 of the voice program).

The organ used to only *log* missing sections and let the concat skip them —
silently shortening the VO and breaking the ``len(sec_files) == len(sections)``
equality the beat-anchor step relies on (a fuzzy-tiling downgrade). This gate
makes those failures LOUD: every section must yield a present, non-silent,
non-clipped wav of plausible duration, and the section↔wav count must match.

Signature is synthesis-free (takes wav paths) so it is unit-testable with crafted
wavs. Mirrors nolan.scriptwriter.gate: typed checks + an ``ok`` verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from nolan.voice_audio import wav_stats

# Registry of what the gate checks — surfaced on /voices (honesty).
VOICE_GATE_CHECKS = [
    ("count", "every script section produced exactly one wav (protects video ≡ narration)"),
    ("present", "the section's wav exists"),
    ("silent", "the section is audible (RMS above the silence floor)"),
    ("too_short", "the section is not truncated (duration ≥ floor and ≥ a fraction of expected)"),
    ("clipped", "the section is not clipped (few samples at full scale)"),
    ("too_long", "the section is not runaway-long vs its word count"),
]


@dataclass
class VoiceCheck:
    id: str
    level: str            # "error" | "warn"
    message: str
    index: Optional[int] = None


@dataclass
class VoiceReport:
    ok: bool
    checks: List[VoiceCheck] = field(default_factory=list)
    sections: List[dict] = field(default_factory=list)   # per-section stats

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [{"id": c.id, "level": c.level, "message": c.message,
                        "index": c.index} for c in self.checks],
            "sections": self.sections,
            "errors": sum(1 for c in self.checks if c.level == "error"),
            "warnings": sum(1 for c in self.checks if c.level == "warn"),
        }

    def summary(self) -> str:
        e = sum(1 for c in self.checks if c.level == "error")
        w = sum(1 for c in self.checks if c.level == "warn")
        head = "; ".join(f"[{c.level}] sec {c.index}: {c.message}" if c.index is not None
                         else f"[{c.level}] {c.message}"
                         for c in self.checks if c.level == "error")[:400]
        return f"voice gate: {e} error(s), {w} warning(s)" + (f" — {head}" if head else "")


def gate_voiceover(sections: List[dict], wavs: List, *, wpm: float = 150.0,
                   min_rms_dbfs: float = -50.0, min_dur_s: float = 0.3,
                   dur_frac_min: float = 0.35, dur_frac_max: float = 3.0,
                   clip_frac_max: float = 0.01) -> VoiceReport:
    """Gate a synthesized VO. ``sections`` = [{title, body}] aligned to ``wavs``
    (each a path or None if that section produced nothing)."""
    checks: List[VoiceCheck] = []
    stats: List[dict] = []

    missing = sum(1 for w in wavs if not w)
    if missing:
        checks.append(VoiceCheck(
            "count", "error",
            f"{missing} of {len(sections)} sections produced no audio — breaks the "
            "section↔beat count invariant (video ≡ narration)"))

    for i, (s, w) in enumerate(zip(sections, wavs)):
        words = len(((s.get("body") if isinstance(s, dict) else "") or "").split())
        expected = round(words / wpm * 60.0, 2) if words else 0.0
        if not w:
            stats.append({"index": i, "present": False, "words": words,
                          "expected_s": expected})
            checks.append(VoiceCheck("present", "error", "no audio produced", index=i))
            continue
        st = wav_stats(w)
        st.update(index=i, present=True, words=words, expected_s=expected,
                  delta_s=(round(st["duration_s"] - expected, 2) if expected else None))
        stats.append(st)

        if st["duration_s"] < min_dur_s or (expected and st["duration_s"] < expected * dur_frac_min):
            checks.append(VoiceCheck(
                "too_short", "error",
                f"{st['duration_s']}s vs ~{expected}s expected for {words} words", index=i))
        if st["rms_dbfs"] < min_rms_dbfs:
            checks.append(VoiceCheck(
                "silent", "error", f"near-silent ({st['rms_dbfs']} dBFS)", index=i))
        if st["clip_frac"] > clip_frac_max:
            checks.append(VoiceCheck(
                "clipped", "warn", f"{st['clip_frac']*100:.1f}% of samples clipped", index=i))
        if expected and st["duration_s"] > expected * dur_frac_max:
            checks.append(VoiceCheck(
                "too_long", "warn",
                f"{st['duration_s']}s is >{dur_frac_max}× the ~{expected}s expected", index=i))

    ok = not any(c.level == "error" for c in checks)
    return VoiceReport(ok=ok, checks=checks, sections=stats)
