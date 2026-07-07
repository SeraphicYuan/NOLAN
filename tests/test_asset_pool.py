"""Asset pool — the derived media-bin view (quality program P1).

The pool is DERIVED (never stored): asset dirs + plan references + shortlist
+ render manifest, with the status ladder in-video > selected > candidate >
shortlisted > unused. "in-video" comes ONLY from output/render_manifest.json,
which ONLY the render step writes (honesty-grepped here).
"""

import json
import re
from pathlib import Path

from nolan.asset_pool import build_pool

SRC = Path(__file__).resolve().parents[1] / "src" / "nolan"


def _proj(tmp_path, scenes=None, shortlist_items=None, manifest_scenes=None):
    """Minimal project: assets/art files + optional plan/shortlist/manifest."""
    art = tmp_path / "assets" / "art"
    art.mkdir(parents=True)
    for name in ("a.jpg", "b.jpg", "c.jpg", "d.mp4"):
        (art / name).write_bytes(b"x")
    if scenes is not None:
        (tmp_path / "scene_plan.json").write_text(
            json.dumps({"sections": {"sec_1": scenes}}), encoding="utf-8")
    if shortlist_items is not None:
        from nolan import shortlist
        shortlist.save(tmp_path, shortlist_items)
    if manifest_scenes is not None:
        out = tmp_path / "output"
        out.mkdir(exist_ok=True)
        (out / "render_manifest.json").write_text(
            json.dumps({"version": 1, "written_by": "render",
                        "scenes": manifest_scenes}), encoding="utf-8")
    return tmp_path


def _by_name(pool):
    return {it["name"]: it for it in pool["items"]}


def test_bare_dir_all_unused(tmp_path):
    pool = build_pool(_proj(tmp_path))
    assert pool["counts"] == {"unused": 4}
    assert pool["has_manifest"] is False
    kinds = {it["name"]: it["kind"] for it in pool["items"]}
    assert kinds["d.mp4"] == "video" and kinds["a.jpg"] == "image"


def test_status_ladder(tmp_path):
    art = "assets/art"
    p = _proj(
        tmp_path,
        scenes=[{
            "id": "scene_001",
            "matched_asset": f"{art}/a.jpg",
            "asset_candidates": [{"src": f"{art}/b.jpg", "score": 0.4}],
        }],
        shortlist_items=[{
            "key": "path:c", "kind": "image",
            "payload": {"op": "add", "source": "path",
                        "path": str(tmp_path / art / "c.jpg")},
        }],
        manifest_scenes={"scene_001": [str(tmp_path / art / "a.jpg")]},
    )
    by = _by_name(build_pool(p))
    # manifest (in-video) outranks the plan's "selected"
    assert by["a.jpg"]["status"] == "in-video"
    assert by["b.jpg"]["status"] == "candidate"
    assert by["c.jpg"]["status"] == "shortlisted"
    assert by["d.mp4"]["status"] == "unused"
    # ladder is strict: plan reference never downgrades a rendered asset
    assert set(by["a.jpg"]["scenes"]["scene_001"]) == {"matched", "rendered"}


def test_scene_role_links_and_license(tmp_path):
    art = "assets/art"
    p = _proj(tmp_path, scenes=[
        {"id": "scene_001", "matched_asset": f"{art}/a.jpg",
         "asset_license": {"license": "PD", "source": "wikimedia",
                           "title": "Aeneas Flees Troy"}},
        {"id": "scene_002",
         "pinned_asset": {"src": f"{art}/b.jpg"},
         "assets": [{"src": f"{art}/c.jpg"}]},
    ])
    pool = build_pool(p)
    by = _by_name(pool)
    assert by["a.jpg"]["scenes"] == {"scene_001": ["matched"]}
    assert by["a.jpg"]["title"] == "Aeneas Flees Troy"
    assert by["a.jpg"]["source"] == "wikimedia"
    assert by["b.jpg"]["scenes"] == {"scene_002": ["pin"]}
    assert by["c.jpg"]["scenes"] == {"scene_002": ["tray"]}
    assert {"b.jpg", "c.jpg"} <= {n for n, it in by.items()
                                  if it["status"] == "selected"}
    assert pool["scenes"] == ["scene_001", "scene_002"]


def test_shortlist_scene_hint_and_note(tmp_path):
    p = _proj(tmp_path, shortlist_items=[{
        "key": "path:b", "kind": "image", "scene_hint": "scene_009",
        "note": "use for the storm beat",
        "payload": {"op": "add", "source": "path",
                    "path": str(tmp_path / "assets/art/b.jpg")},
    }])
    by = _by_name(build_pool(p))
    it = by["b.jpg"]
    assert it["status"] == "shortlisted"
    assert it["scene_hint"] == "scene_009"
    assert it["note"] == "use for the storm beat"
    assert it["shortlist_key"] == "path:b"
    # hint also links the scene (role: shortlist) for the by-scene filter
    assert it["scenes"] == {"scene_009": ["shortlist"]}


def test_missing_file_reported_not_hidden(tmp_path):
    p = _proj(tmp_path, scenes=[{
        "id": "scene_001", "matched_asset": "assets/art/gone.jpg"}])
    by = _by_name(build_pool(p))
    assert by["gone.jpg"]["exists"] is False
    assert by["gone.jpg"]["status"] == "selected"


def test_unreadable_plan_still_lists_files(tmp_path):
    p = _proj(tmp_path)
    (p / "scene_plan.json").write_text("{not json", encoding="utf-8")
    pool = build_pool(p)
    assert pool["counts"] == {"unused": 4}


# --- honesty: ONLY the render step writes the manifest -----------------------

def test_render_manifest_written_only_by_render():
    """The user's rule: only rendering changes usage tags. Grep-enforced:
    the only module that WRITES output/render_manifest.json is
    premium_render (readers are fine)."""
    writers = []
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "render_manifest.json" not in text:
            continue
        # a writer both names the file and write_text's near it
        for m in re.finditer(r"render_manifest\.json", text):
            window = text[m.start():m.start() + 400]
            if "write_text" in window:
                writers.append(f.name)
    assert set(writers) <= {"premium_render.py"}, (
        f"render_manifest.json written outside the render step: {writers}")
    assert "premium_render.py" in writers, (
        "premium_render no longer writes render_manifest.json — "
        "the pool's in-video status has no source")
