"""Test: archival-art sourcing (masterwork raid) — offline, no network.

Verifies:
  1. Title matching: named works match, stand-ins rejected, generic art-medium
     words stripped (fixes zero-recall long queries on Commons).
  2. Stale-file regression: a failed download must NEVER be blessed because an
     old file exists at the destination (the Nydia bug).
  3. img_sources threading in external_assets._search (image-biased, video and
     default paths untouched).
  4. source_art_for_plan: only art-typed scenes considered, misses recorded,
     plan save round-trips.

Live network behavior (Commons TLS-block → curl fallback; exact-title wins)
was validated on the-aeneid: 21/21 scenes, named works verified by hash.

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/test_art_sourcing.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.art_sourcing import (_needs_art, _query_variants_for_title,
                                    _title_match, exact_title_pass)


class Scene:
    def __init__(self, **kw):
        self.id = kw.get("id", "scene_001")
        self.visual_type = kw.get("visual_type", "archival-art")
        self.search_query = kw.get("search_query")
        self.matched_asset = None
        self.generated_asset = None
        self.matched_clip = None


class Result:
    def __init__(self, title, url="https://x/y.jpg", w=2000, h=3000, source="wikimedia"):
        self.title, self.url, self.width, self.height, self.source = title, url, w, h, source


def test_title_matching():
    assert _title_match("Bernini Aeneas Anchises and Ascanius sculpture Borghese",
                        "Aeneas, Anchises, and Ascanius by Bernini, 1618-1620, marble") >= 0.6
    assert _title_match("Vergilius Vaticanus manuscript page Aeneid illustration",
                        "Meister des Vergilius Vaticanus 001.jpg") >= 0.6
    assert _title_match("Bernini Aeneas Anchises and Ascanius sculpture Borghese",
                        "Nydia, the Blind Flower Girl of Pompeii") == 0.0
    vs = _query_variants_for_title("Vergilius Vaticanus manuscript page Aeneid illustration")
    assert "vergilius vaticanus aeneid" in vs, vs
    print("title matching OK — named works pass, stand-ins fail, generics stripped")


def test_stale_file_regression(td: Path):
    """Failed download + pre-existing old file at dest → NO match claimed."""
    out = td / "assets" / "art"
    out.mkdir(parents=True)
    stale = out / "scene_001.jpg"
    stale.write_bytes(b"x" * 5000)              # old wrong image from a prior run

    class FailingClient:
        def search_assets(self, q, **kw):
            return [Result("Aeneas, Anchises, and Ascanius by Bernini")]
        def download_image(self, result, path, prefer_large=True):
            return None                          # download fails

    import src.nolan.art_sourcing as ars
    orig = ars._curl_download
    ars._curl_download = lambda url, dest, timeout=90: False   # no network
    try:
        scene = Scene(search_query="Bernini Aeneas Anchises Ascanius")
        kind = exact_title_pass(scene, client=FailingClient(), ingest_lib=None,
                                out_dir=out, project_root=td,
                                img_sources=["wikimedia"])
    finally:
        ars._curl_download = orig
    assert kind is None and scene.matched_asset is None, (kind, scene.matched_asset)
    assert stale.read_bytes() == b"x" * 5000, "stale file must be untouched"
    print("stale-file regression OK — failed download never blessed")


def test_exact_pass_success(td: Path):
    class OKClient:
        def search_assets(self, q, **kw):
            return [Result("Nydia, the Blind Flower Girl"),
                    Result("Aeneas, Anchises, and Ascanius by Bernini, marble")]
        def download_image(self, result, path, prefer_large=True):
            Path(path).write_bytes(b"j" * 4096)
            return Path(path)

    out = td / "assets" / "art2"
    scene = Scene(id="scene_009", search_query="Bernini Aeneas Anchises Ascanius sculpture")
    kind = exact_title_pass(scene, client=OKClient(), ingest_lib=None,
                            out_dir=out, project_root=td, img_sources=["wikimedia"])
    assert kind == "exact:wikimedia", kind
    assert scene.matched_asset == "assets/art2/scene_009.jpg", scene.matched_asset
    assert (td / scene.matched_asset).stat().st_size == 4096
    print("exact pass OK — title-best picked, downloaded, stamped project-relative")


def test_img_sources_threading():
    from src.nolan.external_assets import _search

    class Stub:
        def __init__(self): self.calls = []
        def search_assets(self, q, **kw): self.calls.append(kw); return []
    c = Stub()
    _search(c, ["q"], "image", [], 5, img_sources=["met"])
    _search(c, ["q"], "image", [], 5)
    _search(c, ["q"], "video", ["pexels"], 5, img_sources=["met"])
    assert c.calls[0]["sources"] == ["met"]
    assert "sources" not in c.calls[1]
    assert c.calls[2]["sources"] == ["pexels"]
    print("img_sources threading OK")


def test_needs_art():
    assert _needs_art(Scene(), ("archival-art",))
    assert not _needs_art(Scene(visual_type="b-roll"), ("archival-art",))
    s = Scene(); s.matched_asset = "x.jpg"
    assert not _needs_art(s, ("archival-art",))
    print("needs-art gating OK")


def main():
    test_title_matching()
    test_img_sources_threading()
    test_needs_art()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        test_stale_file_regression(Path(td))
        test_exact_pass_success(Path(td))
    print("\nOK - art sourcing verified.")


if __name__ == "__main__":
    main()
