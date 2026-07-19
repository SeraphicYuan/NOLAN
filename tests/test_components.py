"""Component-token registry (theme schema v2, Layer 4 — per-theme component bundles).

Docs claim, tests enforce: every component the registry marks `wired` has EACH of its bundle tokens
consumed by a var(--token) reference in the block CSS (composer or the sample seeds). This is exactly the
guard that caught --card-shadow — authored by 24 themes yet read by nothing. A `pending` component may be
unconsumed (that's what pending means). Also: a theme that sets --card-shadow must set a non-empty value.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REG = json.loads((REPO / "themes" / "composition" / "components.json").read_text(encoding="utf-8"))
COMPOSE_SRC = (REPO / "render-service" / "_lab_hyperframes" / "bridge" / "compose.py").read_text(encoding="utf-8")
SEEDS_SRC = (REPO / "themes" / "scripts" / "gen_samples.py").read_text(encoding="utf-8")
SRC = COMPOSE_SRC + SEEDS_SRC
THEMES = sorted(d.name for d in (REPO / "themes").iterdir() if d.is_dir() and (d / "tokens.css").exists())


def test_registry_shape():
    assert REG["components"], "no components"
    for name, c in REG["components"].items():
        assert c.get("status") in ("wired", "pending", "n/a"), f"{name}: bad status"
        assert c.get("tokens"), f"{name}: needs a token bundle"
        # a component that is NOT wired must carry a reason (why pending / why not an axis)
        if c["status"] != "wired":
            assert c.get("_desc"), f"{name}: {c['status']} components must document a reason"


def test_wired_components_have_every_token_consumed():
    for name, c in REG["components"].items():
        if c["status"] != "wired":
            continue
        for role, token in c["tokens"].items():
            assert f"var({token}" in SRC, \
                f"component '{name}' is 'wired' but its {role} token {token} is consumed by no block (phantom)"


def test_card_shadow_is_no_longer_phantom():
    # regression guard for the exact bug Layer 4 fixed: --card-shadow was set by 24 themes, read by nothing
    assert "var(--card-shadow" in SRC, "--card-shadow must be consumed (it was the phantom Layer 4 activated)"
    # and it must keep a fallback so themes that DON'T set it aren't flattened
    assert re.search(r"var\(--card-shadow\s*,", SRC), "--card-shadow consumers must supply a fallback default"


def test_themes_that_set_card_shadow_have_a_value():
    for th in THEMES:
        css = (REPO / "themes" / th / "tokens.css").read_text(encoding="utf-8")
        m = re.search(r"--card-shadow\s*:\s*(.*?);", css, re.S)
        if m:
            assert m.group(1).strip(), f"{th}: --card-shadow is empty (would break box-shadow)"
