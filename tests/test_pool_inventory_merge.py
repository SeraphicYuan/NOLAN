"""`write_inventory` must MERGE into pool.json, not replace it.

The trap: `pool.json.write_text(this_run_only)`. `pool.json` is the project's asset CATALOGUE — the
b-roll build writes it, key-assets adds heroes, `/pool` curation sets `selected`, `add_scene_asset`
appends a hand-dropped file with scene provenance. Whoever wrote last owned all of it, so acquiring a
single asset from the edit loop (which runs the same bridge) would have replaced a 150-entry catalogue
with that run's handful. It survived only because an agent spotted it and hand-placed everything.

Keyed on `file` (the asset's identity on disk), not `id` (the NEED it was fetched for, which repeats
across runs). Curation flags a re-fetch doesn't carry must survive, or a re-run silently un-prunes.
"""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"

_spec = importlib.util.spec_from_file_location("_bridge_pool", BRIDGE / "pool.py")
poolmod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poolmod)


def _item(file, **kw):
    return {"id": kw.pop("id", "a1"), "file": file, "media_type": "image", "caption": "", **kw}


def test_merge_keeps_entries_this_run_never_saw():
    existing = [_item(f"x{i}.jpg") for i in range(150)]
    incoming = [_item("new.jpg", id="a99")]
    out = poolmod.merge_pool(existing, incoming)
    assert len(out) == 151, "the 150-entry catalogue is exactly what the overwrite destroyed"
    assert out[-1]["file"] == "new.jpg"


def test_incoming_wins_per_file_but_order_is_stable():
    existing = [_item("a.jpg", relevance=0.1), _item("b.jpg"), _item("c.jpg")]
    incoming = [_item("b.jpg", relevance=0.9)]
    out = poolmod.merge_pool(existing, incoming)
    assert [e["file"] for e in out] == ["a.jpg", "b.jpg", "c.jpg"]
    assert out[1]["relevance"] == 0.9


def test_curation_survives_a_refetch():
    existing = [_item("a.jpg", selected=False, caption="a human wrote this", flags="watermark")]
    incoming = [_item("a.jpg")]                       # a fresh fetch carries none of those
    out = poolmod.merge_pool(existing, incoming)
    assert out[0]["selected"] is False, "a re-run must not silently un-prune the pool"
    assert out[0]["caption"] == "a human wrote this"
    assert out[0]["flags"] == "watermark"


def test_scene_provenance_survives():
    existing = [_item("s1_edit_pic1.jpg", scene_id="s1", frame_id="01-beat")]
    out = poolmod.merge_pool(existing, [_item("s1_edit_pic1.jpg")])
    assert out[0]["scene_id"] == "s1" and out[0]["frame_id"] == "01-beat"


def test_backslash_paths_are_the_same_asset():
    out = poolmod.merge_pool([_item("videos/a.mp4")], [_item("videos\\a.mp4", relevance=0.5)])
    assert len(out) == 1, "a Windows-separator path is not a second asset"


def test_rows_without_a_file_are_dropped_not_crashed():
    assert poolmod.merge_pool([{"id": "junk"}], [_item("a.jpg")]) == [_item("a.jpg")]


def test_write_inventory_merges_by_default(tmp_path, monkeypatch):
    project = tmp_path / "p"
    (project / "capture" / "extracted").mkdir(parents=True)
    (project / "pool.json").write_text(json.dumps([_item("old.jpg")]), encoding="utf-8")
    poolmod.write_inventory([_item("new.jpg")], project)
    got = json.loads((project / "pool.json").read_text(encoding="utf-8"))
    assert {e["file"] for e in got} == {"old.jpg", "new.jpg"}


def test_write_inventory_can_still_replace_deliberately(tmp_path):
    project = tmp_path / "p"
    (project / "capture" / "extracted").mkdir(parents=True)
    (project / "pool.json").write_text(json.dumps([_item("old.jpg")]), encoding="utf-8")
    poolmod.write_inventory([_item("new.jpg")], project, merge=False)
    got = json.loads((project / "pool.json").read_text(encoding="utf-8"))
    assert [e["file"] for e in got] == ["new.jpg"], "a cold rebuild must still be possible, explicitly"


def test_a_corrupt_pool_json_does_not_lose_the_new_run(tmp_path):
    project = tmp_path / "p"
    (project / "capture" / "extracted").mkdir(parents=True)
    (project / "pool.json").write_text("{ this is not json", encoding="utf-8")
    poolmod.write_inventory([_item("new.jpg")], project)
    got = json.loads((project / "pool.json").read_text(encoding="utf-8"))
    assert [e["file"] for e in got] == ["new.jpg"]
