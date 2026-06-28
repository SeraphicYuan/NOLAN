"""Phases 2-3: unified description-based b-roll match (library-first + ingest)."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from nolan.external_assets import scene_query_text, semantic_match_for_scene
from nolan.imagelib.store import ImageLibrary


def _scene(**kw):
    base = dict(id="s1", narration_excerpt="", visual_description="",
                search_query="", visual_type="b-roll", matched_asset=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_scene_query_text_combines_fields():
    s = _scene(narration_excerpt="the great war", visual_description="a muddy trench",
               search_query="ww1 soldiers")
    q = scene_query_text(s)
    assert "great war" in q and "muddy trench" in q and "ww1 soldiers" in q


def test_phase2_library_first(tmp_path):
    lib = ImageLibrary("global", base_dir=tmp_path / "lib")
    img = tmp_path / "t.png"
    Image.new("RGB", (320, 240), (100, 40, 40)).save(img)
    lib.add_file(img, source="curated",
                 description="a soldier crouched in a muddy WW1 trench under heavy fire",
                 embed=False)

    scene = _scene(narration_excerpt="life in the trenches of the great war",
                   visual_description="soldiers dug into a trench")
    out = tmp_path / "out"; out.mkdir()
    kind = semantic_match_for_scene(
        scene, libs=[lib], client=None, scorer=None, vid_sources=[],
        out_dir=out, project_root=tmp_path, ingest_lib=None, sim_gate=0.2)

    assert kind and kind.startswith("library")
    assert scene.matched_asset and (tmp_path / scene.matched_asset).exists()


def test_phase2_no_match_below_gate(tmp_path):
    lib = ImageLibrary("global", base_dir=tmp_path / "lib")
    img = tmp_path / "t.png"
    Image.new("RGB", (320, 240), (40, 100, 40)).save(img)
    lib.add_file(img, source="curated",
                 description="a bowl of fresh fruit on a kitchen table", embed=False)
    scene = _scene(narration_excerpt="naval warfare and battleships at sea",
                   visual_description="warships firing")
    out = tmp_path / "out"; out.mkdir()
    kind = semantic_match_for_scene(
        scene, libs=[lib], client=None, scorer=None, vid_sources=[],
        out_dir=out, project_root=tmp_path, ingest_lib=None, sim_gate=0.45)
    assert kind is None
    assert scene.matched_asset is None


def test_phase3_external_ingest(tmp_path, monkeypatch):
    # describer maps any ingested image to a fixed description
    lib = ImageLibrary("global", base_dir=tmp_path / "lib",
                       describer=lambda p: "a vast empty desert with sand dunes at sunset")

    cand = SimpleNamespace(url="http://example/desert.jpg", source="ddgs",
                           source_url=None, license="cc0", title="dune",
                           description=None, width=800, height=600, tags=None,
                           media_type="image")

    class Client:
        def search_assets(self, q, **k):
            return [cand]

    class Scorer:
        def calculate_quality_score(self, c):
            return (10, {})

    # offline: ingest's download writes a real local image
    import nolan.http_client as hc

    def fake_dl(url, dest, headers=None):
        Image.new("RGB", (800, 600), (200, 150, 80)).save(dest)
    monkeypatch.setattr(hc, "download_file_sync", fake_dl)

    scene = _scene(narration_excerpt="crossing the empty desert",
                   visual_description="endless sand dunes")
    out = tmp_path / "out"; out.mkdir()
    kind = semantic_match_for_scene(
        scene, libs=[lib], client=Client(), scorer=Scorer(), vid_sources=[],
        out_dir=out, project_root=tmp_path, ingest_lib=lib, sim_gate=0.2)

    assert kind and kind.startswith("ingest")
    assert scene.matched_asset and (tmp_path / scene.matched_asset).exists()
    # the described candidate now lives in the library for reuse
    assert lib.search_by_description("desert dunes", k=1)
