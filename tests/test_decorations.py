"""Signature-decoration registry (composition-DNA lever #3, docs/REFERENCE_TEMPLATE_ANALYSIS.md).

Docs claim, tests enforce: the decoration registry (themes/composition/decorations.json) and the
composer's renderers (compose._DECOR_RENDERERS) are in PARITY (no device without an executor, no
executor without a catalog entry), every theme's declared `decoration` names a real device, and a
declared decoration actually renders."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for p in (str(REPO / "src"), str(BRIDGE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import compose  # noqa: E402

REGISTRY = json.loads((REPO / "themes" / "composition" / "decorations.json").read_text(encoding="utf-8"))
DEVICES = REGISTRY["devices"]


def test_registry_loads_and_is_shaped():
    assert REGISTRY.get("version") and DEVICES
    for did, spec in DEVICES.items():
        assert {"group", "kind", "scope", "purpose"} <= set(spec), f"{did} missing fields"
        assert spec["kind"] in ("shared", "signature")
        assert spec["scope"] in ("frame", "scene")


def test_registry_and_renderers_are_in_parity():
    reg = set(DEVICES)
    impl = set(compose._DECOR_RENDERERS)
    assert reg == impl, (f"registry↔renderer drift — in registry only: {reg - impl}; "
                         f"in compose only: {impl - reg}")


def test_every_theme_decoration_names_a_real_device():
    reg = set(DEVICES)
    for tj in (REPO / "themes").glob("*/theme.json"):
        meta = json.loads(tj.read_text(encoding="utf-8"))
        for d in (meta.get("decoration") or []):
            did = d if isinstance(d, str) else d.get("id")
            assert did in reg, f"{tj.parent.name}: decoration {did!r} not in the registry {sorted(reg)}"


def test_declared_decoration_renders_and_bare_theme_is_empty():
    # a decorated theme emits the overlay with its devices; an un-decorated theme emits nothing
    deco = compose._theme_decorations("blueprint")                      # graph-paper + compass-rings
    assert 'class="decor' in deco and "background-size:3.2cqw" in deco  # graph-paper (stable on blueprint)
    # pick a theme with no `decoration` key
    bare = next(t.parent.name for t in (REPO / "themes").glob("*/theme.json")
                if "decoration" not in json.loads(t.read_text(encoding="utf-8")))
    assert compose._theme_decorations(bare) == "", f"{bare} should render no decoration"


def test_param_devices_honour_their_param():
    # test the param-carrying renderers directly (decoupled from any theme's current assignment):
    # a {id, text} spec must reach the renderer's output
    assert "Field Notes" in compose._DECOR_RENDERERS["rail-label"]({"text": "Field Notes"})
    assert "Handmade" in compose._DECOR_RENDERERS["rosette-seal"]({"text": "Handmade"})
    assert "BOLD" in compose._DECOR_RENDERERS["letterpress"]({"text": "BOLD"})
    assert "bash" in compose._DECOR_RENDERERS["os-chrome"]({"text": "~/nolan — bash"})
