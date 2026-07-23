"""Narration registers — per-story-type delivery + calibrated pace.

A register bundles (a) an ``instruct`` that sets the narrator's CHARACTER, (b) a measured
``base_wpm`` (the natural pace that instruct produces at speed 1.0, calibrated on a fixed
reference beat), and (c) a ``target_wpm`` you actually want. The executor applies a global
``speed = target_wpm / base_wpm`` on the single synthesis pass, so an un-tagged beat reads in
the register's character AT the target average pace — the model's own intra-beat rubato is
preserved (one model load, no sentence chopping). Per-beat ``[delivery:]`` tags still override
the instruct (character); the global speed still applies on top.

Why this shape: an instruct alone gets you into the right *range* but won't hit a number — a
real narrator of "this story type" sits ~175 wpm, and only base_wpm→speed makes ``target_wpm``
a knob you can trust. See docs memory: our continuous synthesis already matches human
intra-beat variation (stdev ~29); the only real gap was overall tempo, which this controls.

Module contract:
  registry        — NARRATION_REGISTERS (here)
  authored field  — project.yaml ``narration_register: <name>`` (read_project_register)
  executor        — resolve_register(...).instruct / .speed, applied in synthesize_voiceover
  honesty test    — tests/test_voice_registers.py (base_wpm measured, speed in safe band)

``base_wpm`` values are CALIBRATED (measured on the 259-word De Beers "Move one" beat,
CosyVoice3 clone of beat-the-noise-narrator, 2026-07-23). Re-calibrate if you change an
instruct — the number is only meaningful for the exact wording above it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# A target/base ratio outside this band means the instruct doesn't match the target — re-word
# the instruct rather than stretching the audio into time-stretch artifact territory.
_SPEED_MIN, _SPEED_MAX = 0.75, 1.35


@dataclass(frozen=True)
class NarrationRegister:
    name: str
    instruct: str          # narrator CHARACTER (also the baseline for un-tagged beats)
    base_wpm: int          # MEASURED natural pace of `instruct` at speed 1.0
    target_wpm: int        # desired average; executor applies speed = target/base
    when_to_use: str

    @property
    def speed(self) -> float:
        """Global speed that lifts base_wpm to target_wpm, clamped to the safe band."""
        s = self.target_wpm / self.base_wpm
        return round(max(_SPEED_MIN, min(_SPEED_MAX, s)), 3)


NARRATION_REGISTERS: dict[str, NarrationRegister] = {
    "narrative-investigative": NarrationRegister(
        "narrative-investigative",
        "an energetic, engaging storyteller keeping the pace brisk and lively",
        base_wpm=164, target_wpm=175,
        when_to_use="deep-dive / investigative video essays that carry the viewer through a "
                    "story (De Beers, etc.) — the default register"),
    "explainer": NarrationRegister(
        "explainer",
        "a clear, measured teacher explaining things step by step",
        base_wpm=157, target_wpm=155,
        when_to_use="how-it-works / tutorial content where clarity beats drama"),
    "contemplative": NarrationRegister(
        "contemplative",
        "a calm, reflective narrator, unhurried and thoughtful",
        base_wpm=138, target_wpm=135,
        when_to_use="reflective, somber, or philosophical pieces that need room to breathe"),
    "punchy-news": NarrationRegister(
        "punchy-news",
        "a sharp, urgent newsreader driving the story forward fast",
        base_wpm=177, target_wpm=190,
        when_to_use="fast recaps, news, or high-energy montages"),
}

DEFAULT_REGISTER = "narrative-investigative"


def resolve_register(name: str | None) -> NarrationRegister:
    """Register by name; falls back to the default for None or an unknown name."""
    return NARRATION_REGISTERS.get(name or DEFAULT_REGISTER,
                                   NARRATION_REGISTERS[DEFAULT_REGISTER])


def read_project_register(base: Path) -> str | None:
    """Read ``narration_register`` from a project's project.yaml (None if absent/unreadable)."""
    p = Path(base) / "project.yaml"
    if not p.exists():
        return None
    try:
        import yaml
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        v = doc.get("narration_register")
        return str(v).strip() if v else None
    except Exception:
        return None
