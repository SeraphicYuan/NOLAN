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


# --- isotype ---

def test_isotype_resolves_items_and_composes_icons():
    from nolan.data.resolve import resolve_scene
    import compose
    ds = _DS([{"m": "A", "v": 8}, {"m": "B", "v": 64}], ["m", "v"])
    out = resolve_scene({"type": "isotype", "data": {"encode": {"label": "m", "value": "v"}}}, ds)
    assert out["data"]["items"] == [{"value": 8, "label": "A"}, {"value": 64, "label": "B"}]
    f, t = compose.BLOCKS["isotype"]("is", {"id": "is", "type": "isotype", "start": 0, "dur": 9,
        "data": {"items": [{"label": "A", "value": 8}, {"label": "B", "value": 16}], "per": 8}})
    html = "".join(f)
    assert "is-i0-0" in html and "is-i1-0" in html                # unit icons per item
    assert _classified("isotype") == ("dataviz", True)


# --- dumbbell ---

def test_dumbbell_resolves_start_end_and_composes_gap():
    from nolan.data.resolve import resolve_scene
    import compose
    ds = _DS([{"c": "X", "lo": 3, "hi": 38}], ["c", "lo", "hi"])
    out = resolve_scene({"type": "dumbbell", "data": {"encode": {"label": "c", "start": "lo", "end": "hi"}}}, ds)
    assert out["data"]["items"] == [{"label": "X", "start": 3, "end": 38}]
    f, t = compose.BLOCKS["dumbbell"]("db", {"id": "db", "type": "dumbbell", "start": 0, "dur": 9,
        "data": {"items": [{"label": "X", "start": 3, "end": 38}]}})
    html = "".join(f)
    assert "db-bar0" in html and "db-s0" in html and "db-e0" in html   # gap bar + two dots
    assert any("scaleX" in x for x in t)                              # the gap grows (seek-safe)
    assert _classified("dumbbell") == ("dataviz", True)


# --- small_multiples ---

def test_small_multiples_groups_rows_into_panels():
    from nolan.data.resolve import resolve_scene
    import compose
    ds = _DS([{"g": "P1", "x": "a", "y": 5}, {"g": "P1", "x": "b", "y": 9},
              {"g": "P2", "x": "a", "y": 2}], ["g", "x", "y"])
    out = resolve_scene({"type": "small_multiples", "data": {"encode": {"panel": "g", "x": "x", "y": "y"}}}, ds)
    panels = out["data"]["panels"]
    assert [p["label"] for p in panels] == ["P1", "P2"]              # grouped, order preserved
    assert panels[0]["series"] == [{"label": "a", "value": 5}, {"label": "b", "value": 9}]
    f, t = compose.BLOCKS["small_multiples"]("sm", {"id": "sm", "type": "small_multiples", "start": 0, "dur": 9,
        "data": {"panels": panels}})
    html = "".join(f)
    assert "sm-p0" in html and "sm-p1" in html and "sm-p0-b0" in html   # a panel per group, bars within
    assert _classified("small_multiples") == ("dataviz", True)


# --- histogram ---

def test_histogram_bins_a_raw_column():
    from nolan.data.resolve import resolve_scene
    import compose
    ds = _DS([{"v": v} for v in (1, 1, 2, 3, 9, 10)], ["v"])
    out = resolve_scene({"type": "histogram", "data": {"encode": {"value": "v", "bins": 3}}}, ds)
    bins = out["data"]["bins"]
    assert len(bins) == 3 and sum(b["count"] for b in bins) == 6     # every value binned exactly once
    assert bins[0]["count"] == 4 and bins[-1]["count"] == 2          # skewed toward the low bins
    f, t = compose.BLOCKS["histogram"]("hg", {"id": "hg", "type": "histogram", "start": 0, "dur": 9,
        "data": {"bins": bins, "marker": 8}})
    html = "".join(f)
    assert "hg-b0" in html and "hg-mk" in html                       # bars + the marker line
    assert any("scaleY" in x for x in t)
    assert _classified("histogram") == ("dataviz", True)
