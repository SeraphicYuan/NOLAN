"""Overlay-plate library resolver (nolan.effects.library) — a JSON manifest merged with a dir scan
(mirrors the music/sfx libraries), repo-anchored, resolving an effect tag to a plate path and reporting
which element tags are stocked (so the UI/gate can be honest about fire/rain availability)."""
import json

from nolan.effects import library as lib


def _mk(tmp_path):
    (tmp_path / "fire-1.mp4").write_bytes(b"\0")
    (tmp_path / "rain-2.mp4").write_bytes(b"\0")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")          # non-video ignored
    (tmp_path / "overlays.json").write_text(json.dumps([
        {"file": "fire-1.mp4", "effect": "fire", "blend": "screen", "tags": ["flame"], "license": "Pixabay"},
    ]), encoding="utf-8")
    return tmp_path


def test_load_merges_manifest_and_scans_dir(tmp_path):
    items = lib.load_overlay_library(_mk(tmp_path))
    assert {i["file"] for i in items} == {"fire-1.mp4", "rain-2.mp4"}   # .txt ignored, both videos found
    fire = next(i for i in items if i["file"] == "fire-1.mp4")
    assert fire["effect"] == "fire" and fire["blend"] == "screen" and fire["license"] == "Pixabay"
    rain = next(i for i in items if i["file"] == "rain-2.mp4")          # unmanifested → effect from stem, blend default
    assert rain["effect"] == "rain" and rain["blend"] == "screen"


def test_resolve_and_stocked(tmp_path):
    d = _mk(tmp_path)
    assert lib.resolve_plate("fire", d).endswith("fire-1.mp4")
    assert lib.resolve_plate("nope", d) is None
    assert lib.stocked_effects(d) == {"fire", "rain"}


def test_missing_library_is_empty(tmp_path):
    assert lib.load_overlay_library(tmp_path / "nope") == []
    assert lib.resolve_plate("fire", tmp_path / "nope") is None


def test_real_library_has_all_element_plates():
    """The 8 element/damage plate tags the registry declares are actually stocked (the CC0 set is committed)."""
    from nolan.effects.registry import REGISTRY
    want = {e.plate for e in REGISTRY if e.method == "blend_overlay" and e.plate}
    have = lib.stocked_effects()
    assert want <= have, f"unstocked element plates: {want - have}"


def test_manifest_is_fetchable_and_licensed():
    """The committed manifest carries a direct download URL + license for every plate — so the gitignored
    .mp4 binaries are reproducible on a fresh clone via `nolan effects fetch-plates`."""
    manifest = lib.OVERLAY_LIBRARY / "overlays.json"
    if not manifest.exists():
        import pytest
        pytest.skip("no overlays manifest")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    assert entries
    for e in entries:
        assert e.get("file") and e.get("effect"), f"entry missing file/effect: {e}"
        assert str(e.get("url", "")).startswith("http"), f"{e.get('file')}: no fetch url"
        assert e.get("license"), f"{e.get('file')}: no license recorded"


def test_fetch_plates_command_is_registered():
    from nolan.cli import main
    assert "effects" in main.commands and "fetch-plates" in main.commands["effects"].commands
