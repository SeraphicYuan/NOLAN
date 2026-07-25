"""Block capabilities have ONE home, and it must match the composer.

INCIDENT: `_GROUND_BLOCKS` existed twice, same name, different contents — autoground's 6 (derived from
which composer fns call `media_ground`) and metrics' `{"statement","stat"}`. Auto-ground placed grounds
on pull_quote/ledger/bullet_list/comparison_table, the composer RENDERED them, and `scene_media()`
scored them `none`: no coverage credit, and still flagged as long ungrounded holds. 11 scenes in the
diamond-v2 run. Unifying them moved coverage 0.656 -> 0.767 and long-holds 11 -> 2 with no re-authoring.

These tests keep the registry honest against compose.py AND keep the consumers from re-forking it.
"""
import re
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
SRC = Path(__file__).resolve().parents[1] / "src" / "nolan"


def _composer_ground_blocks() -> set:
    """Re-derive the truth: registered templates whose composer fn calls media_ground()."""
    consuming, registry = set(), {}
    for name in ("compose.py", "compose_extension.py"):
        src = (BRIDGE / name).read_text(encoding="utf-8")
        bounds = [(m.start(), m.group(1)) for m in re.finditer(r"^def (\w+)\(", src, re.M)] + [(len(src), "")]
        for i in range(len(bounds) - 1):
            fn = bounds[i][1]
            if fn != "media_ground" and "media_ground(" in src[bounds[i][0]:bounds[i + 1][0]]:
                consuming.add(fn)
        reg = re.search(r"^(?:BLOCKS|EXT_BLOCKS) = \{(.*?)\n?\}", src, re.S | re.M)
        assert reg, f"{name}: block registry not found (regex drift?)"
        registry.update(dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1))))
    assert len(registry) >= 45, f"only parsed {len(registry)} templates — the registry regex drifted"
    return {t for t, fn in registry.items() if fn in consuming}


def test_registry_matches_the_composer():
    from nolan.block_registry import GROUND_BLOCKS
    assert set(GROUND_BLOCKS) == _composer_ground_blocks()


def test_consumes_ground_helper_agrees():
    from nolan.block_registry import GROUND_BLOCKS, consumes_ground
    assert consumes_ground("statement") and consumes_ground("pull_quote")
    assert not consumes_ground("hero") and not consumes_ground("chart")
    assert all(consumes_ground(b) for b in GROUND_BLOCKS)


def test_no_module_keeps_a_PRIVATE_copy_of_the_ground_set():
    """The whole point: a second definition is how the two truths happened. Consumers must IMPORT."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "block_registry.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # a literal set/frozenset assigned to a *_GROUND_BLOCKS name is a fork; an import is fine
        if re.search(r"^_?GROUND_BLOCKS\s*[:=].*[{(]\s*[\"']", text, re.M):
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"these re-declare the ground set instead of importing it: {offenders}"


def test_both_consumers_actually_import_it():
    for rel in ("hyperframes/autoground.py", "style_contract/metrics.py"):
        text = (SRC / rel).read_text(encoding="utf-8")
        assert "block_registry import GROUND_BLOCKS" in text, f"{rel} must read the shared registry"


# --- phantom reveal cues (postmortem item 4) --------------------------------------------------

def _composer_cue_blocks() -> set:
    """Re-derive: registered templates whose composer reads the author-supplied `at`."""
    import re
    src, registry = {}, {}
    for name in ("compose.py", "compose_extension.py"):
        src[name] = (BRIDGE / name).read_text(encoding="utf-8")
        reg = re.search(r"^(?:BLOCKS|EXT_BLOCKS) = \{(.*?)\n?\}", src[name], re.S | re.M)
        registry.update(dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1))))

    def body(fn):
        for s in src.values():
            i = s.find(f"def {fn}(")
            if i < 0:
                continue
            j = s.find("\ndef ", i + 1)
            return s[i:j if j > 0 else len(s)]
        return ""

    reads = re.compile(r"""get\(\s*["']at["']|\[["']at["']\]|_reveal_cues\(|_reveal_times\(""")
    return {t for t, fn in registry.items() if reads.search(body(fn))}


def test_cue_registry_matches_the_composer():
    from nolan.block_registry import CUE_BLOCKS
    assert set(CUE_BLOCKS) == _composer_cue_blocks()


def test_find_cue_fields_walks_nested_elements():
    """A top-level check misses every real cue — they are written on events/items/steps."""
    from nolan.block_registry import find_cue_fields
    assert find_cue_fields({"events": [{"year": "1888", "at": 3.0}, {"year": "1902", "at": 7.0}]}) == [
        "data.events[0].at", "data.events[1].at"]
    assert find_cue_fields({"steps": [{"label": "one"}], "title": "no cues"}) == []
    assert find_cue_fields({"at": True}) == []          # a bool is not a cue time


def test_the_gate_refuses_a_cue_on_a_block_that_ignores_it():
    """REGRESSION: a timeline with events[].at validated rc=0 "OK" and the cue did nothing — the
    phantom-field class. timeline does not even DECLARE `at` in its schema."""
    src = (BRIDGE / "author.py").read_text(encoding="utf-8")
    assert "consumes_cues" in src and "find_cue_fields" in src
    assert "INERT" in src, "the error must say WHY, not just that it is invalid"
