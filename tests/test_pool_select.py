"""HF-pool refine-scope (hyperframes/pool_select.py) — human selection shapes the author's menu."""
import json

from nolan.hyperframes import pool_select


def _pool():
    return [
        {"id": "a1", "file": "a1_00.jpg", "media_type": "image", "caption": "a logo", "source": "ddgs", "selected": True},
        {"id": "a1", "file": "a1_01.jpg", "media_type": "image", "caption": "another", "source": "ddgs", "selected": False},
        {"id": "a2", "file": "videos/a2_00.mp4", "media_type": "video", "caption": "a clip", "source": "pexels_video"},
    ]  # a2 has no flag → default in


def test_render_inventory_lines_filters_selected():
    body = "\n".join(pool_select.render_inventory_lines(_pool()))
    assert "a1_00.jpg" in body and "videos/a2_00.mp4" in body   # selected + default-in
    assert "a1_01.jpg" not in body                              # deselected → excluded from the menu
    assert "[video]" in body


def test_set_pool_selected_toggles_and_rewrites_menu(tmp_path):
    (tmp_path / "pool.json").write_text(json.dumps(_pool()), encoding="utf-8")
    assert pool_select.set_pool_selected(tmp_path, "a1_00.jpg", False) is True
    pool = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
    assert next(i for i in pool if i["file"] == "a1_00.jpg")["selected"] is False
    inv = (tmp_path / "capture" / "extracted" / "asset-descriptions.md").read_text(encoding="utf-8")
    assert "a1_00.jpg" not in inv and "a2_00.mp4" in inv        # menu re-written filtered on toggle
    assert pool_select.set_pool_selected(tmp_path, "nope.jpg", True) is False


def test_write_inventory_from_pool_count(tmp_path):
    (tmp_path / "pool.json").write_text(json.dumps(_pool()), encoding="utf-8")
    assert pool_select.write_inventory_from_pool(tmp_path) == 2   # a1_00 + a2_00; a1_01 excluded
