"""Build the LLM-facing capability manifest + prompt guide from the registry."""
from __future__ import annotations

import json
from typing import Any, Dict

from .registry import REGISTRY, SHARED, ANCHORS, THEMES, Param, MotionEffect


def _param(p: Param) -> Dict[str, Any]:
    d: Dict[str, Any] = {"type": p.type}
    if p.doc:
        d["doc"] = p.doc
    if p.values is not None:
        d["values"] = p.values
    if p.required:
        d["required"] = True
    if p.default is not None:
        d["default"] = p.default
    return d


def _effect(e: MotionEffect) -> Dict[str, Any]:
    return {
        "effect": e.id,
        "backend": e.backend,
        "category": e.category,
        "purpose": e.purpose,
        "content": {p.name: _param(p) for p in e.content},
        "style": {p.name: _param(p) for p in e.style},
        "shared": e.shared,
    }


def build_manifest() -> Dict[str, Any]:
    """Machine-readable capability description for the LLM."""
    return {
        "shared": {
            "position": {"doc": SHARED["position"].doc, "anchors": list(ANCHORS.keys()),
                         "or": "{x, y} in 0..1", "default": "center"},
            "theme": {"values": THEMES, "default": "dark-editorial"},
            "accent": {"doc": SHARED["accent"].doc, "type": "color"},
        },
        "effects": [_effect(e) for e in REGISTRY],
    }


def build_guide() -> str:
    """System prompt that teaches the LLM to emit a valid spec."""
    manifest = build_manifest()
    return (
        "You translate a one-line video-essay scene design into a precise render spec for "
        "NOLAN's motion library. Choose the single best effect for the intent.\n\n"
        "Output ONLY a JSON object:\n"
        '  {"effect": <id>, "content": {...}, "style": {...}, "position": <anchor|{x,y}>, '
        '"theme": <name>, "accent": <hex?>}\n'
        "Rules:\n"
        "- Use exactly the content/style field names listed for the chosen effect.\n"
        "- Only include `position`/`theme`/`accent` if the effect lists them under `shared`.\n"
        "- `position` is a named anchor or {x,y} in 0..1. Omit -> center. Default theme dark-editorial.\n"
        "- Pick `style` enum values from the allowed list; omit to use the default.\n"
        '- Numbers: put a leading sign/currency in `prefix` ("+", "$") and units in `suffix` '
        '("%", "B", "x"). Use "+" for growth/increase (e.g. "+300%").\n\n'
        "CAPABILITY MANIFEST:\n" + json.dumps(manifest, separators=(",", ":")) + "\n\n"
        "EXAMPLES:\n"
        'Scene: "circle the 88% stat, hand-drawn, top-left"\n'
        '{"effect":"annotate-stat","content":{"value":"88%","label":"of the S&P 500"},'
        '"style":{"shapeStyle":"scribble"},"position":"top-left","theme":"dark-editorial"}\n'
        'Scene: "AI capex 520B vs dot-com 160B, glass bars"\n'
        '{"effect":"bar-compare","content":{"title":"AI capex vs the dot-com peak","prefix":"$",'
        '"suffix":"B","bars":[{"label":"Dot-com peak","value":160},{"label":"AI capex","value":520}]},'
        '"style":{"barStyle":"glass"},"theme":"dark-editorial"}\n'
    )
