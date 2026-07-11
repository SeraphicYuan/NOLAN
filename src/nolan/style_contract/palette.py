"""The block PALETTE — surfaced into the author's brief so it evaluates every beat against the FULL
menu instead of defaulting to a few familiar blocks.

The catalog (compose.py/catalog.json) already carries rich per-block metadata (purpose / when_to_use
/ not_for). The gap the v1 essay exposed is not availability — it's that an LLM with the whole menu
in context still satisfices on the archetypal blocks (statement/stat/comparison) and never reaches
the long tail (chart/timeline/gallery/…). Two counters, both generated FROM the catalog so they
can't rot: a compact cheat-sheet (every block, one line) + a beat→block routing table that forces
the tail into consideration ("this beat is a TREND → you must consider chart/timeline").
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


def _default_catalog_path() -> Path:
    return (Path(__file__).resolve().parents[3] / "render-service" / "_lab_hyperframes"
            / "bridge" / "catalog.json")


def load_catalog(path: Optional[str] = None) -> Dict:
    return json.loads(Path(path or _default_catalog_path()).read_text(encoding="utf-8"))


def catalog_blocks(catalog: Optional[Dict] = None) -> List[str]:
    return sorted((catalog or load_catalog()).get("scene_templates", {}))


# beat "shape" → candidate blocks. Naming the shape first is the discipline that pulls the long
# tail into consideration instead of free-associating to statement.
BEAT_ROUTING = [
    ("a single number / metric", "stat"),
    ("a TREND or ranking across ≥3 values or times", "chart · timeline"),
    ("a direct contrast (X vs Y, before/after, promise vs reality)", "comparison"),
    ("a SET shown at once (examples, faces, screenshots, evidence)", "gallery · carousel · collage"),
    ("a sequence of events over time", "timeline"),
    ("a relationship / ownership / flow / how-it-connects", "diagram"),
    ("a place / where it happens", "geo"),
    ("a quote, headline, or named source moment", "newshead"),
    ("a claim or rhetorical turn carried by words", "statement"),
    ("a person's name + role", "lower_third"),
    ("a social post / message screenshot", "social_card"),
    ("a document, filing, or page as evidence", "document"),
    ("code or a config snippet", "code"),
    ("a logo / line-art draw-on", "linedraw"),
    ("a full-screen PHOTO or CLIP under the words", "statement/newshead with ground:{kind:image|video}"),
]


def palette_brief(catalog: Optional[Dict] = None) -> str:
    """A compact cheat-sheet of the whole palette + the beat→block routing, for the author's brief."""
    cat = catalog or load_catalog()
    st = cat.get("scene_templates", {})
    lines = [f"FULL BLOCK PALETTE ({len(st)} templates) — evaluate EVERY beat against this menu; do "
             "not default to statement/stat/comparison. Use each block's richer options too "
             "(comparison takes video sides + effects; grounds can be image or video):"]
    for name in sorted(st):
        e = st[name]
        wt = (e.get("when_to_use") or e.get("purpose") or "").strip().rstrip(".")
        nf = (e.get("not_for") or "").strip().rstrip(".")
        lines.append(f"- {name}: {wt}" + (f"  [not for: {nf}]" if nf else ""))
    lines.append("BEAT → BLOCK routing — name the beat's SHAPE first, then pick from its candidates:")
    for shape, blocks in BEAT_ROUTING:
        lines.append(f"- {shape} → {blocks}")
    return "\n".join(lines)


def authoring_brief(contract, catalog: Optional[Dict] = None) -> str:
    """The full author-facing brief: the style contract's targets + the palette menu/routing.
    This is what gets injected into the kickoff brief (`compile_brief` = craft targets; palette =
    the menu the author must actually shop from)."""
    return contract.compile_brief() + "\n\n" + palette_brief(catalog)
