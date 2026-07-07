"""The preview harness covers every motion effect — no component silently skipped.

The showcase gallery shows a rendered clip per catalog entry; that promise only
holds if the harness has a fixture for each. This pins motion coverage at 100%
so a new motion effect can't ship without its preview fixture. (Block-template
coverage is reported by the harness itself; motion is the enforced floor.)
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_fixtures():
    spec = importlib.util.spec_from_file_location(
        "gen_showcase_previews", REPO / "scripts" / "gen_showcase_previews.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FIXTURES


def test_every_motion_effect_has_a_preview_fixture():
    from nolan.webui.showcase_catalog import build_showcase_catalog
    fixtures = _load_fixtures()
    cat = build_showcase_catalog(REPO)
    motion = {e["id"] for e in cat["effects"] if e["kind"] == "motion"}
    # annotate-video needs sample video footage the harness doesn't ship; allow-list it.
    allowed_missing = {"annotate-video"}
    missing = motion - set(fixtures) - allowed_missing
    assert not missing, f"motion effects with no preview fixture: {sorted(missing)}"


def test_every_block_template_has_a_fixture_or_shares_one():
    from nolan.webui.showcase_catalog import build_showcase_catalog
    fixtures = _load_fixtures()
    cat = build_showcase_catalog(REPO)
    block = {e["id"] for e in cat["effects"] if e["kind"] == "block"}
    motion = {e["id"] for e in cat["effects"] if e["kind"] == "motion"}
    # a block id that also exists as a motion effect shares that preview (dedupe).
    missing = block - set(fixtures) - motion
    assert not missing, f"block templates with no preview fixture: {sorted(missing)}"


def test_block_fixtures_produce_a_valid_adapter():
    from nolan import layout_blocks
    fixtures = _load_fixtures()
    from nolan.webui.showcase_catalog import build_showcase_catalog
    cat = build_showcase_catalog(REPO)
    block_ids = {e["id"] for e in cat["effects"] if e["kind"] == "block"}
    motion_ids = {e["id"] for e in cat["effects"] if e["kind"] == "motion"}
    for bid in block_ids - motion_ids:            # the ones rendered as blocks
        fx = fixtures.get(bid)
        assert fx, f"{bid} has no fixture"
        adapted = layout_blocks.adapt(bid, dict(fx.get("content", {})))
        assert adapted is not None, f"block fixture for {bid} produces no adapter (bad sample params)"
