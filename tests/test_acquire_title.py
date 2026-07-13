"""Title-aware retrieval for NAMED-work essays (holbein POST_MORTEM #3).

CLIP clusters a named series (all 46 Holbein woodcuts at 0.29-0.36) and can't pick 'THE PLOUGHMAN'
— it even ranked THE WAGGONER above THE KNIGHT. Two guards:
  1. ImageLibrary.search_by_title leads with the titled asset (lexical, no CLIP).
  2. acquire_need lets a strong title match stand in for relevance, so the named artifact clears the
     library floor AND ranks first — instead of relying on the VLM cull to rescue it.
"""
from pathlib import Path

import pytest

from nolan.acquire.config import AcquireConfig
from nolan.acquire.engine import Candidate, Context, acquire_need
from nolan.imagelib.store import ImageLibrary


def _png(path: Path, quadrant: int):
    """A decodable 800x600 image with a distinct white quadrant (so avg_hash differs -> not deduped)."""
    from PIL import Image
    im = Image.new("RGB", (800, 600), (0, 0, 0))
    x0, y0 = (0, 0) if quadrant in (0, 1) else (400, 300)
    for x in range(x0, x0 + 400):
        for y in range(y0, y0 + 300):
            im.putpixel((x, y), (255, 255, 255))
    im.save(path)
    return path


# ---- store: lexical title retrieval --------------------------------------------------------------
def test_search_by_title_ranks_named_work(tmp_path):
    lib = ImageLibrary(base_dir=tmp_path / "lib")
    lib.add_file(_png(tmp_path / "p.png", 0), title="THE PLOUGHMAN.", license="PD", embed=False)
    lib.add_file(_png(tmp_path / "k.png", 3), title="THE KNIGHT.", license="PD", embed=False)

    hits = lib.search_by_title("the ploughman")
    assert [h.asset.title for h in hits] == ["THE PLOUGHMAN."]     # exact named work, knight excluded
    # verbose beat query still fully matches the short title
    assert lib.search_by_title("a ploughman driven by death")[0].asset.title == "THE PLOUGHMAN."
    # un-named / descriptive query matches no title -> empty (CLIP will handle it)
    assert lib.search_by_title("skeletons dancing in a procession") == []


# ---- engine: the title boost survives CLIP re-scoring + the floor --------------------------------
def test_title_match_leads_and_clears_floor(tmp_path):
    p_plough = _png(tmp_path / "plough.png", 0)
    p_knight = _png(tmp_path / "knight.png", 3)
    plough = Candidate(ref="plough", source="library", modality="image", path=p_plough,
                       meta={"source": "library", "title_cover": 1.0, "title": "THE PLOUGHMAN."})
    knight = Candidate(ref="knight", source="library", modality="image", path=p_knight,
                       meta={"source": "library", "title_cover": 0.0, "title": "THE KNIGHT."})

    ctx = Context(
        search_library=lambda q, n: [plough, knight],
        relevance=lambda text, path: 0.10,        # CLIP can't tell them apart AND is below the 0.24 floor
    )
    cfg = AcquireConfig(sources=("library",), generate_evocative=False)
    kept = acquire_need({"id": "n1", "query": "the ploughman", "category": "art"},
                        ctx, cfg, tmp_path, [])

    refs = [c.ref for c in kept]
    assert "plough" in refs                        # title match rescued it past the floor
    assert kept[0].ref == "plough"                 # and it leads
    assert "knight" not in refs                    # no title + CLIP 0.10 < 0.24 floor -> culled
    assert kept[0].relevance >= 0.24               # relevance was boosted to the title cover
