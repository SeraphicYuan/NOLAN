"""Shape scale (theme schema v2, Layer 3 — corner radius + border weight as a theme axis).

Docs claim, tests enforce: the scale's tokens (--r-card, --bw) are CONSUMED by the card-family block CSS
(phantom-field guard); a theme that sets --bw uses a value from the registry's border-weight ladder (the
scale, not an arbitrary width); and the axis actually separates shape characters (a brutalist theme's border
is heavier than a gallery theme's).
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REG = json.loads((REPO / "themes" / "composition" / "shape_scale.json").read_text(encoding="utf-8"))
COMPOSE_SRC = (REPO / "render-service" / "_lab_hyperframes" / "bridge" / "compose.py").read_text(encoding="utf-8")
SEEDS_SRC = (REPO / "themes" / "scripts" / "gen_samples.py").read_text(encoding="utf-8")
THEMES = sorted(d.name for d in (REPO / "themes").iterdir() if d.is_dir() and (d / "tokens.css").exists())


def _bw(theme):
    m = re.search(r"^\s*--bw\s*:\s*([^;]+);", (REPO / "themes" / theme / "tokens.css").read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else None


def test_registry_shape():
    assert REG["radius"]["_var"] == "--r-card" and REG["radius"]["steps"]
    bw = REG["border-weight"]
    assert bw["_var"] == "--bw" and bw["default"] == "2px"
    assert set(bw["steps"]) == {"hair", "thin", "base", "bold", "heavy"}


def test_scale_tokens_are_consumed():
    # --bw + --r-card must be read by the card-family CSS (composer + the framed seed) — no dead axis
    assert "var(--bw" in COMPOSE_SRC or "var(--bw" in SEEDS_SRC
    assert "var(--bw" in SEEDS_SRC, "the framed seed border must consume --bw"
    assert COMPOSE_SRC.count("var(--r-card") >= 3, "card-family radii should read --r-card"


def test_themes_use_ladder_border_weights():
    allowed = set(REG["border-weight"]["steps"].values()) | {REG["border-weight"]["default"]}
    for th in THEMES:
        bw = _bw(th)
        if bw is not None:
            assert bw in allowed, f"{th}: --bw {bw!r} not a border-weight ladder step {sorted(allowed)}"


def test_axis_separates_shape_character():
    # brutalist heavier than gallery — the axis carries real character, not noise
    def px(v):
        return float(v.replace("px", "")) if v else 2.0
    assert px(_bw("bauhaus-bold")) > px(_bw("vellum")), "brutalist border should exceed gallery hairline"
    assert px(_bw("neubrutalism")) >= 3, "a brutalist theme should be at bold+ weight"
    assert px(_bw("newsroom")) <= 1.5, "an editorial theme should be hairline/thin"
