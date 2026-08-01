"""Normalize placeholder or Nolan style payloads into Manim-facing tokens."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from math_animation.contracts import StrictModel, StyleTemplateRef


class TypographyTokens(StrictModel):
    font: str | None = None
    title_size: int = Field(default=64, ge=16, le=160)
    body_size: int = Field(default=34, ge=12, le=96)
    math_size: int = Field(default=58, ge=16, le=160)


class MotionTokens(StrictModel):
    create_seconds: float = Field(default=1.0, gt=0)
    transform_seconds: float = Field(default=1.2, gt=0)
    beat_hold_seconds: float = Field(default=0.4, ge=0)


class StyleTokens(StrictModel):
    background: str = "#0c0c0b"
    foreground: str = "#faf9f5"
    muted: str = "#b0aea5"
    semantic_colors: dict[str, str] = Field(
        default_factory=lambda: {
            "primary": "#6a9bcc",
            "secondary": "#d4a27f",
            "changing": "#d97757",
            "fixed": "#788c5d",
            "positive": "#70a37f",
            "negative": "#c96a6a",
        }
    )
    typography: TypographyTokens = Field(default_factory=TypographyTokens)
    motion: MotionTokens = Field(default_factory=MotionTokens)
    raw_provider_payload: dict[str, Any] = Field(default_factory=dict)

    def color_for(self, role: str) -> str:
        if role == "foreground":
            return self.foreground
        if role == "muted":
            return self.muted
        return self.semantic_colors.get(role, self.semantic_colors["primary"])


def _nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def normalize_style(reference: StyleTemplateRef) -> StyleTokens:
    """Map recognized placeholder keys while retaining Nolan's full payload.

    The adapter intentionally accepts a few conventional spellings. Once Nolan's
    schema is available this function can be replaced without changing project,
    screenplay, compiler, or timeline contracts.
    """

    raw = reference.raw
    colors = raw.get("colors", {}) if isinstance(raw.get("colors"), dict) else {}
    semantic = (
        raw.get("semantic_colors", {})
        if isinstance(raw.get("semantic_colors"), dict)
        else {}
    )
    defaults = StyleTokens()
    typography = TypographyTokens(
        font=_nested(raw, "typography", "font"),
        title_size=_nested(
            raw, "typography", "title_size", default=defaults.typography.title_size
        ),
        body_size=_nested(
            raw, "typography", "body_size", default=defaults.typography.body_size
        ),
        math_size=_nested(
            raw, "typography", "math_size", default=defaults.typography.math_size
        ),
    )
    motion = MotionTokens(
        create_seconds=_nested(
            raw, "motion", "create_seconds", default=defaults.motion.create_seconds
        ),
        transform_seconds=_nested(
            raw,
            "motion",
            "transform_seconds",
            default=defaults.motion.transform_seconds,
        ),
        beat_hold_seconds=_nested(
            raw,
            "motion",
            "beat_hold_seconds",
            default=defaults.motion.beat_hold_seconds,
        ),
    )
    return StyleTokens(
        background=colors.get("background", raw.get("background", defaults.background)),
        foreground=colors.get("foreground", raw.get("foreground", defaults.foreground)),
        muted=colors.get("muted", defaults.muted),
        semantic_colors={**defaults.semantic_colors, **semantic},
        typography=typography,
        motion=motion,
        raw_provider_payload=raw,
    )
