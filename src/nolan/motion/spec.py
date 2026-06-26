"""Validate + normalize a motion spec against the registry."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .registry import get_effect, SHARED, THEMES, Param


def _coerce(value: Any, p: Param) -> Any:
    try:
        if p.type == "int":
            return int(str(value).replace(",", "")) if not isinstance(value, int) else value
        if p.type == "number":
            return float(value)
    except (ValueError, TypeError):
        return p.default
    return value


def validate(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return (normalized_spec, errors). Missing required content -> errors (non-fatal:
    defaults are still filled so a render can be attempted). Invalid enums/shared are
    dropped to defaults with a recorded message."""
    errors: List[str] = []
    eff_id = spec.get("effect")
    effect = get_effect(eff_id)
    if effect is None:
        return spec, [f"unknown effect '{eff_id}'"]

    out: Dict[str, Any] = {"effect": effect.id, "backend": effect.backend, "target": effect.target}

    # content
    content_in = spec.get("content", {}) or {}
    content: Dict[str, Any] = {}
    for p in effect.content:
        if p.name in content_in and content_in[p.name] not in (None, ""):
            content[p.name] = _coerce(content_in[p.name], p)
        elif p.required:
            errors.append(f"missing required content '{p.name}'")
            content[p.name] = p.default if p.default is not None else ""
        elif p.default is not None:
            content[p.name] = p.default
    out["content"] = content

    # style (enums)
    style_in = spec.get("style", {}) or {}
    style: Dict[str, Any] = {}
    for p in effect.style:
        v = style_in.get(p.name, p.default)
        if p.type == "enum" and p.values and v not in p.values:
            if p.name in style_in:
                errors.append(f"style '{p.name}'='{v}' invalid -> default '{p.default}'")
            v = p.default
        if v is not None:
            style[p.name] = _coerce(v, p)
    out["style"] = style

    # shared (only those the effect supports)
    if "position" in effect.shared:
        out["position"] = spec.get("position", SHARED["position"].default)
    if "theme" in effect.shared:
        t = spec.get("theme", SHARED["theme"].default)
        if t not in THEMES:
            errors.append(f"theme '{t}' invalid -> dark-editorial")
            t = "dark-editorial"
        out["theme"] = t
    if "accent" in effect.shared and spec.get("accent"):
        out["accent"] = spec["accent"]

    out["duration"] = float(spec.get("duration", effect.duration_default))
    return out, errors
