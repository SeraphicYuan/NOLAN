"""The preview scaffold stages assets BY REFERENCE, not by copying the whole tree.

Incident this pins: `_scaffold_preview` did `for f in (comp/'assets').rglob('*')` on EVERY
snapshot / proposal-preview / frame-render call. Measured on the-diamond-illusion-v3 — an 856 MB
asset tree and 12 scratch dirs = 7.5 GB under `compositions/_preview` — so a 25-proposal batch
would copy ~21 GB before rendering a single pixel, and the "cheap verify before you render" loop
was unusable on exactly the footage-heavy comps that most need it.

What must hold:
  * an asset the frame REFERENCES is staged (from the composed HTML *or* the spec — a video ground
    composes to a transparent div, so its path exists only in the spec);
  * the frame's voice wav is staged (the scaffold mounts it as a root <audio>);
  * an asset the frame does NOT reference is NOT staged;
  * staging twice does no work the second time (hardlink/identical-file reuse).
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import edit as hfedit           # noqa: E402


@pytest.fixture()
def comp():
    name = "_hf_preview_staging_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    frame = {"id": "01-beat", "dur": 8.0, "scenes": [
        {"id": "s1", "type": "statement", "start": 0, "dur": 4,
         "data": {"lines": ["hello"], "ground": {"kind": "image", "src": "assets/used_still.jpg"}}},
        {"id": "s2", "type": "statement", "start": 4, "dur": 4,
         # a VIDEO ground: composes to a transparent div, so this path is ONLY in the spec
         "data": {"lines": ["world"], "ground": {"kind": "video", "src": "assets/used_clip.mp4"}}},
    ]}
    (fdir / "01-beat.spec.json").write_text(json.dumps({"frames": [frame]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"highlighter-editorial"}', encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps(
        {"voices": [{"frame": 1, "path": "assets/voice/01.wav", "duration_s": 8.0}]}), encoding="utf-8")
    adir = dst / "assets"
    (adir / "voice").mkdir(parents=True)
    (adir / "used_still.jpg").write_bytes(b"\xff\xd8" + b"S" * 4096)
    (adir / "used_clip.mp4").write_bytes(b"V" * 8192)
    (adir / "voice" / "01.wav").write_bytes(b"RIFF" + b"W" * 2048)
    (adir / "unused_huge.mp4").write_bytes(b"U" * (2 * 1024 * 1024))   # the whole-tree copy's cost
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


def test_referenced_assets_span_html_spec_and_voice(comp):
    html = '<div class="clip" style="background-image:url(\'assets/used_still.jpg\')"></div>'
    refs = hfedit._referenced_assets(comp, "01-beat", html)
    assert "assets/used_still.jpg" in refs
    assert "assets/used_clip.mp4" in refs, "a video ground lives only in the spec — scan it too"
    assert "assets/voice/01.wav" in refs, "the scaffold mounts the frame's voice as a root <audio>"
    assert "assets/unused_huge.mp4" not in refs


def test_scaffold_stages_only_referenced(comp):
    html = '<div class="clip" style="background-image:url(\'assets/used_still.jpg\')"></div>'
    pdir = hfedit._scaffold_preview(comp, "01-beat", html_text=html, preview_id="_t1")
    assert (pdir / "assets" / "used_still.jpg").is_file()
    assert (pdir / "assets" / "used_clip.mp4").is_file()
    assert (pdir / "assets" / "voice" / "01.wav").is_file()
    assert not (pdir / "assets" / "unused_huge.mp4").exists(), \
        "the 2 MB unreferenced asset is the whole-tree-copy cost this fix exists to remove"
    staged = sum(f.stat().st_size for f in (pdir / "assets").rglob("*") if f.is_file())
    tree = sum(f.stat().st_size for f in (hfedit._comp_dir(comp) / "assets").rglob("*") if f.is_file())
    assert staged < tree / 4, f"staged {staged} of {tree} bytes — reference staging did not bite"


def test_restaging_is_a_no_op(comp):
    html = '<div style="background-image:url(\'assets/used_still.jpg\')"></div>'
    pdir = hfedit._scaffold_preview(comp, "01-beat", html_text=html, preview_id="_t2")
    dest = pdir / "assets" / "used_still.jpg"
    before = dest.stat().st_mtime_ns
    hfedit._scaffold_preview(comp, "01-beat", html_text=html, preview_id="_t2")
    assert dest.stat().st_mtime_ns == before, "an already-staged, identical asset must not be re-written"


def test_prune_previews_reports_what_it_freed(comp):
    html = '<div style="background-image:url(\'assets/used_still.jpg\')"></div>'
    hfedit._scaffold_preview(comp, "01-beat", html_text=html, preview_id="_t3")
    res = hfedit.prune_previews(comp)
    assert res["removed"] >= 1 and res["bytes"] > 0
    assert not (hfedit._comp_dir(comp) / "compositions" / "_preview" / "_t3").exists()
