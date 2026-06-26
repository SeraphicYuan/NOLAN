"""Compile a natural-language scene design into a validated motion spec via the LLM."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .manifest import build_guide
from .spec import validate


def _extract_json(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in LLM output: {text[:200]}")
    return json.loads(m.group(0))


async def compile_spec(scene_design: str, client, repair: bool = True) -> Tuple[Dict[str, Any], List[str]]:
    """scene_design -> (normalized_spec, errors). `client` is a text LLM with async
    generate(prompt, system_prompt). On validation errors, optionally re-asks once."""
    guide = build_guide()
    raw = await client.generate(scene_design, system_prompt=guide)
    try:
        spec = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        spec = {}
    norm, errors = validate(spec)

    if errors and repair:
        fix_prompt = (
            f"Scene: {scene_design}\nYour spec had problems: {errors}\n"
            f"Previous: {json.dumps(spec)}\nReturn a corrected JSON spec only."
        )
        raw2 = await client.generate(fix_prompt, system_prompt=guide)
        try:
            norm2, errors2 = validate(_extract_json(raw2))
            if len(errors2) < len(errors):
                return norm2, errors2
        except (ValueError, json.JSONDecodeError):
            pass
    return norm, errors


async def compile_many(scene_designs: List[str], client) -> List[Tuple[Dict[str, Any], List[str]]]:
    out = []
    for s in scene_designs:
        out.append(await compile_spec(s, client))
    return out
