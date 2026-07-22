"""New dataset-bound data-viz blocks (video-essay forms): resolve materializer + compose executor +
classification. Each block: (1) the resolver fills the block's data shape from encode; (2) the compose
executor emits its signature elements with a seek-safe (strokeDashoffset / opacity) reveal; (3) it is
classified into an archetype + block family (so the catalog can't rot).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "render-service" / "_lab_hyperframes" / "bridge"))


class _DS:
    """A tiny in-memory dataset stub (provenance present so the binding validates)."""
    def __init__(self, rows, cols):
        self.id = "t"
        self.rows = rows
        self.meta = {"provenance": "test"}
        self.columns = [{"name": c} for c in cols]


def _classified(block):
    from nolan.style_contract.metrics import BLOCK_FAMILY
    arch = json.loads((REPO / "themes" / "composition" / "archetypes.json").read_text(encoding="utf-8"))
    in_arch = any(block in v.get("blocks", []) for v in arch["archetypes"].values())
    return BLOCK_FAMILY.get(block), in_arch


# --- slope ---

def test_slope_resolves_start_end_per_series():
    from nolan.data.resolve import resolve_scene
    ds = _DS([{"m": "A", "s": 6, "e": 88}, {"m": "B", "s": 82, "e": 9}], ["m", "s", "e"])
    out = resolve_scene({"type": "slope", "data": {"encode": {"label": "m", "start": "s", "end": "e"}}}, ds)
    assert out["data"]["series"] == [{"label": "A", "start": 6, "end": 88}, {"label": "B", "start": 82, "end": 9}]
    assert out["data"]["value_source"] == "test"


def test_slope_compose_emits_a_drawn_line_per_series():
    import compose
    f, t = compose.BLOCKS["slope"]("sl", {"id": "sl", "type": "slope", "start": 0, "dur": 9, "data": {
        "series": [{"label": "A", "start": 6, "end": 88}, {"label": "B", "start": 82, "end": 9}], "highlight": 0}})
    html = "".join(f)
    assert "sl-ln0" in html and "sl-ln1" in html                 # one slope line per series
    assert any("strokeDashoffset" in x for x in t)               # seek-safe draw (no chart lib)


def test_slope_is_classified():
    fam, in_arch = _classified("slope")
    assert fam == "dataviz" and in_arch
