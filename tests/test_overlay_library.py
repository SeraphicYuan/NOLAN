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


def test_stocked_plates_match_registry_no_orphans():
    """Stocked plates map to real element/damage effect tags (no orphan files) and the library is
    populated. Element effects MAY be plate-pending (declared but unstocked) — a valid degraded state
    (resolve_plate → None → the UI shows '(no plate)'); completeness is a curation choice, not an invariant."""
    from nolan.effects.registry import REGISTRY
    declared = {e.plate for e in REGISTRY if e.method == "blend_overlay" and e.plate}
    have = lib.stocked_effects()
    assert have, "no plates stocked"
    assert have <= declared, f"orphan plate(s) with no registry effect: {have - declared}"


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
        assert e.get("license"), f"{e.get('file')}: no license recorded"
        assert str(e.get("url", "")).startswith("http") or e.get("source"), \
            f"{e.get('file')}: no url and no source — not reproducible/attributable"


def test_fetch_plates_command_is_registered():
    from nolan.cli import main
    assert "effects" in main.commands and "fetch-plates" in main.commands["effects"].commands
    assert "add-plate" in main.commands["effects"].commands


def test_add_plate_copies_records_and_replaces(tmp_path):
    """The `add_plate` seam (behind `nolan effects add-plate`): copy a plate into the library named
    <effect>-<id>, record provenance in overlays.json, and REPLACE a prior plate for the same effect."""
    import shutil
    import subprocess
    from nolan.ffmpeg_utils import FFMPEG
    src = tmp_path / "src"
    src.mkdir()
    vid = src / "12345_small.mp4"
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "color=black:s=64x36:d=1", "-pix_fmt", "yuv420p", str(vid)],
                   capture_output=True)
    libdir = tmp_path / "lib"
    e = lib.add_plate(vid, "rain", blend="screen",
                      provenance={"pixabay_id": 12345, "url": "http://x/y.mp4", "license": "Pixabay"}, library=libdir)
    assert e["file"] == "rain-12345.mp4" and (libdir / "rain-12345.mp4").exists()
    man = json.loads((libdir / "overlays.json").read_text(encoding="utf-8"))
    assert man[0]["effect"] == "rain" and man[0]["url"] == "http://x/y.mp4" and man[0]["blend"] == "screen"
    vid2 = src / "67890_small.mp4"
    shutil.copy(vid, vid2)
    lib.add_plate(vid2, "rain", provenance={"pixabay_id": 67890}, library=libdir)   # replace
    man = json.loads((libdir / "overlays.json").read_text(encoding="utf-8"))
    assert len(man) == 1 and man[0]["file"] == "rain-67890.mp4"
    assert not (libdir / "rain-12345.mp4").exists() and lib.resolve_plate("rain", libdir).endswith("rain-67890.mp4")
