"""Plan-time named-entity coverage check (nolan.acquire.coverage) — POST_MORTEM #8.

The narration can name a subject nothing can depict ('pope' said 4x, no pope woodcut). This locks the
pure parse/probe/check path — a named subject the library title-match and pool caption BOTH miss is a
loud gap; one either covers is fine.
"""
from pathlib import Path

from nolan.acquire import coverage
from nolan.imagelib.store import ImageLibrary


def _png(path: Path, color=(30, 30, 30)):
    from PIL import Image
    Image.new("RGB", (800, 600), color).save(path)        # distinct colors → distinct content hash (no dedup)
    return path


def test_parse_entities_dedups_and_normalizes():
    raw = '```json\n[{"name":"The Pope","kind":"person","mentions":4},' \
          '{"name":"the pope","kind":"person"}, {"name":"","kind":"x"}, "Knight"]\n```'
    ents = coverage.parse_entities(raw)
    names = [e["name"] for e in ents]
    assert names == ["The Pope", "Knight"]                 # deduped (case), blanks dropped, bare str ok
    assert ents[0]["mentions"] == 4 and ents[1]["mentions"] == 1


def test_probe_pool_matches_caption():
    pool = [{"id": "a1", "caption": "a skeletal Death drags a resisting abbot", "query": "the abbot"}]
    assert coverage.probe_pool("abbot", pool) is not None
    assert coverage.probe_pool("pope", pool) is None


def test_check_coverage_flags_named_gap(tmp_path):
    lib = ImageLibrary(base_dir=tmp_path / "lib")
    lib.add_file(_png(tmp_path / "abbot.png", (200, 0, 0)), title="THE ABBOT.", license="PD", embed=False)
    lib.add_file(_png(tmp_path / "knight.png", (0, 0, 200)), title="THE KNIGHT.", license="PD", embed=False)

    entities = [{"name": "the abbot", "kind": "person", "mentions": 2},
                {"name": "the knight", "kind": "person", "mentions": 1},
                {"name": "the pope", "kind": "person", "mentions": 4}]
    rep = coverage.check_coverage(entities, library=lib)

    covered_names = {c["name"] for c in rep["covered"]}
    assert covered_names == {"the abbot", "the knight"}    # both have a titled woodcut
    assert [g["name"] for g in rep["gaps"]] == ["the pope"]  # the corpus has no pope
    assert rep["gaps"][0]["mentions"] == 4                  # loudest gap first


def test_pool_covers_when_library_does_not(tmp_path):
    lib = ImageLibrary(base_dir=tmp_path / "lib")           # empty library
    entities = [{"name": "printing press", "kind": "object", "mentions": 1}]
    pool = [{"id": "p1", "caption": "an antique printing press in a workshop", "query": "printing press"}]
    rep = coverage.check_coverage(entities, library=lib, pool=pool)
    assert not rep["gaps"] and rep["covered"][0]["in_pool"]
