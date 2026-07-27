"""`data.ground`: what the catalog DECLARES and what the composer RENDERS must be the same set.

INCIDENT: catalog.json declared `ground` on all 14 Tier-2 blocks and not one of them read it. An
author who grounded an `isotype` got a validating spec, a clean gate, and a flat page — the
phantom-field class (WIRING_CHECKLIST #1), across a whole tier, for as long as those blocks lived in
a second file no gate read.

Both directions matter. Declared-but-ignored is the phantom above; rendered-but-undeclared is worse
in its own way — a capability no author can discover.
"""
import json
import re
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))["scene_templates"]

sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

# blocks whose ground is painted by a DIFFERENT mechanism than data.ground (their own full-bleed art)
EXEMPT = {"raw"}


def _body(fn: str) -> str:
    i = SRC.find(f"def {fn}(")
    if i < 0:
        return ""
    j = SRC.find("\ndef ", i + 1)
    return SRC[i:j if j > 0 else len(SRC)]


def _renders_ground(block: str) -> bool:
    body = _body(CATALOG.get(block, {}).get("fn") or block)
    return bool(re.search(r"_data_ground\(|media_ground\(", body))


def _declares_ground(block: str) -> bool:
    return "ground" in (CATALOG.get(block, {}).get("data_schema") or {})


def test_declared_ground_is_actually_rendered():
    phantom = sorted(b for b in CATALOG
                     if b not in EXEMPT and _declares_ground(b) and not _renders_ground(b))
    assert not phantom, ("catalog declares `ground` on blocks whose composer never reads it "
                        f"(a spec that validates and renders nothing): {phantom}")


def test_rendered_ground_is_declared():
    undocumented = sorted(b for b in CATALOG
                          if b not in EXEMPT and _renders_ground(b) and not _declares_ground(b))
    assert not undocumented, f"these render a ground no author can discover: {undocumented}"


def test_a_grounded_tier2_block_paints_the_image():
    """Live, not by grep: the image URL must reach the HTML, and the ground must carry its drift."""
    cases = {
        "isotype": {"items": [{"label": "a", "value": 20}]},
        "gauge": {"value": 50, "label": "x"},
        "data_table": {"columns": ["a"], "rows": [["1"]]},
        "process": {"steps": [{"label": "one"}, {"label": "two"}]},
        "bar_race": {"steps": ["t1", "t2"], "series": [{"label": "s", "values": [1, 2]}]},
    }
    for block, data in cases.items():
        sc = {"id": "p", "start": 0.0, "dur": 12.0,
              "data": dict(data, ground={"kind": "image", "src": "assets/probe.jpg"})}
        frag, tl = compose.BLOCKS[block]("p", sc)
        assert "assets/probe.jpg" in "".join(frag), f"{block} dropped its ground"
        assert any("-dgnd" in t for t in tl), f"{block} renders the ground but never drifts it"


def test_the_ground_sits_behind_the_content():
    """Ground on track 0, veil on 1, the block's own content on 2 — a block that kept its opaque
    wrapper on track 1 would paint over the image it just staged."""
    sc = {"id": "p", "start": 0.0, "dur": 10.0,
          "data": {"items": [{"label": "a", "value": 8}],
                   "ground": {"kind": "image", "src": "assets/probe.jpg"}}}
    html = "".join(compose.BLOCKS["isotype"]("p", sc)[0])
    gnd = re.search(r'<div id="p-dgnd"[^>]*data-track-index="(\d+)"', html)
    wrap = re.search(r'<div id="p-wrap"[^>]*data-track-index="(\d+)"', html)
    assert gnd and wrap, html[:400]
    assert int(gnd.group(1)) < int(wrap.group(1)), "the content is painted UNDER the ground"


def test_a_data_block_paints_a_themed_page_background():
    """A data block with no authored ground must still paint the theme's page colour.

    Kept from a MISDIAGNOSIS worth recording: a frame-level render of the gauge came back black, and I
    read it as "a track-0 clip renders outside the `#root` scope where the theme tokens live". The
    shipped video disproved it — `diagram` and `geo` both put a themed background on track 0 and render
    correctly. The real cause was my own probe harness: its mount div omitted `data-composition-id`,
    which production sets, so the runtime never scoped the sub-composition's CSS and every `var(--…)`
    resolved to nothing. The product was fine. Reproduce a render the way production assembles it, or
    the render lies to you.
    """
    import re
    for block in ("gauge", "isotype", "chart"):
        sc = {"id": "p", "start": 0.0, "dur": 9.0,
              "data": {"items": [{"value": 40, "label": "x"}], "series": [{"label": "a", "value": 2}],
                       "bins": [{"x0": 0, "x1": 2, "count": 1}]}}
        html = "".join(compose.BLOCKS[block]("p", sc)[0])
        assert re.search(r'style="[^"]*background:[^"]*var\(--', html), \
            f"{block} paints no themed background at all"
