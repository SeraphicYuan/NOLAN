"""Theme -> authoring brief (the compose-first layout dialect).

The wiring that lets an authoring agent design IN a theme's composition character instead of
treating the theme as a bare, "don't touch" name. It fuses three registries the agent otherwise
never sees together:

  - `themes/<theme>/theme.json` — the theme's identity: composition.{default,allowed} archetype
    dialect, typePersonality, decoration marks, mood.
  - `themes/composition/archetypes.json` (via `nolan.composition`) — what each allowed archetype
    MEANS (intent), so "editorial-column" is a described macro-layout, not a bare token.
  - `themes/composition/layout_variants.json` — per-block arrangement variants, filtered to the
    ones this theme SANCTIONS (a variant's `zone` is an archetype id; keep only zone in allowed).

The deterministic composer (`compose.py::_resolve_variant`) already CONSTRAINS + varies layout to
this same dialect even if the agent sets nothing — so this brief exists for the MEANING-aware
override: pick `hero-single` for a killer number, `banner-top` for a turn. Single source of truth
(reads the live registries), so the menu can't drift from what the composer will accept.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[3]
THEMES = REPO / "themes"
VARIANTS_PATH = THEMES / "composition" / "layout_variants.json"


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _theme_meta(theme: str) -> dict:
    return _load_json(THEMES / str(theme) / "theme.json") or {}


def _layout_variants() -> dict:
    return (_load_json(VARIANTS_PATH) or {}).get("blocks", {})


def _archetype_intents() -> dict:
    """archetype id -> one-line intent (via the shared registry; empty on import failure)."""
    try:
        import sys
        if str(REPO / "src") not in sys.path:
            sys.path.insert(0, str(REPO / "src"))
        from nolan import composition as C
        return {aid: (spec or {}).get("intent", "") for aid, spec in C.archetypes().items()}
    except Exception:
        return {}


def theme_layout_brief(theme: Optional[str], blocks: Optional[List[str]] = None) -> str:
    """A ready-to-inject markdown brief describing a theme's composition dialect + the layout variants
    it sanctions, per block. Returns "" when the theme is unknown / declares no composition (the
    composer then applies no constraint, so an empty brief is honest — nothing to steer toward)."""
    if not theme:
        return ""
    meta = _theme_meta(theme)
    comp = meta.get("composition") or {}
    allowed = comp.get("allowed") or []
    if not allowed:
        return ""
    default = comp.get("default")
    intents = _archetype_intents()
    name = meta.get("name") or theme
    personality = meta.get("typePersonality")
    decoration = meta.get("decoration") or []
    variants = _layout_variants()

    L: List[str] = []
    L.append(f"## This theme's composition dialect — **{name}** (`{theme}`)")
    L.append("The theme is not just colour + type: it declares the macro layouts it belongs in, and the "
             "composer CONSTRAINS every block's arrangement to this set. Author IN this dialect — do not "
             "hand-pick colours (the tokens are applied automatically), but DO choose beat-appropriate "
             "layouts from the menu below.")
    if default:
        L.append(f"- **Default macro-layout:** `{default}` — {intents.get(default, '').strip() or 'the theme resting layout'}")
    L.append("- **Sanctioned macro-layouts (archetypes):**")
    for aid in allowed:
        L.append(f"    - `{aid}` — {intents.get(aid, '').strip() or 'a permitted layout'}")
    if personality:
        L.append(f"- **Type personality:** `{personality}` — lean into it when choosing what carries a beat "
                 f"(a display face wants a hero word / number, not a paragraph).")
    mark_bits = []
    for d in decoration:
        if isinstance(d, dict):
            did = d.get("id") or d.get("kind") or ""
            txt = d.get("text")
            mark_bits.append(f"`{did}`" + (f' ("{txt}")' if txt else ""))
        elif isinstance(d, str):
            mark_bits.append(f"`{d}`")
    if mark_bits:
        L.append(f"- **Signature marks to design AROUND:** {', '.join(mark_bits)}. These sit at the frame's "
                 f"edges/margins — keep hero content in the safe centre so a mark never collides with it.")

    # Per-block, the theme-SANCTIONED variants (zone in allowed). This is the menu the agent picks from.
    L.append("")
    L.append("### Layout variants per block (set `data.variant`; omit to let the composer pick a theme-fitting one)")
    L.append("Vary the arrangement across beats — the composer already rotates + avoids repeats, but YOU pick "
             "the one the beat's *meaning* calls for (a single killer number → a hero layout; a turn → a banner).")
    order = blocks or list(variants.keys())
    any_block = False
    for block in order:
        reg = variants.get(block)
        if not reg:
            continue
        vmap = reg.get("variants", {})
        dflt = reg.get("default")
        # the block's default is ALWAYS available (its canonical form); the theme filters the extra variety.
        sanctioned = [(vid, m) for vid, m in vmap.items() if m.get("zone") in allowed or vid == dflt]
        if not sanctioned:
            continue
        any_block = True
        dflt = reg.get("default")
        dflt_note = f"default `{dflt}`; " if dflt else ""
        L.append(f"- **{block}** — {dflt_note}choose:")
        for vid, m in sanctioned:
            fits = m.get("fits")
            fit_note = f" (best for {fits[0]}–{fits[1]} items)" if isinstance(fits, list) and len(fits) == 2 and fits[0] != fits[1] else ""
            L.append(f"    - `{vid}` — {m.get('desc', '').strip()}{fit_note}")
    if not any_block:
        return ""  # theme sanctions no registered variants for any block — nothing to brief
    return "\n".join(L)
