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
    for name in ("compose.py",):          # ONE composer since the 2026-07-26 extension merge
        src = (BRIDGE / name).read_text(encoding="utf-8")
        bounds = [(m.start(), m.group(1)) for m in re.finditer(r"^def (\w+)\(", src, re.M)] + [(len(src), "")]
        for i in range(len(bounds) - 1):
            fn = bounds[i][1]
            if fn != "media_ground" and "media_ground(" in src[bounds[i][0]:bounds[i + 1][0]]:
                consuming.add(fn)
        reg = re.search(r"^BLOCKS = \{(.*?)\n?\}", src, re.S | re.M)
        assert reg, f"{name}: block registry not found (regex drift?)"
        registry.update(dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1))))
    assert len(registry) >= 45, f"only parsed {len(registry)} templates — the registry regex drifted"
    return {t for t, fn in registry.items() if fn in consuming}


def test_registry_matches_the_composer():
    from nolan.block_registry import GROUND_BLOCKS
    assert set(GROUND_BLOCKS) == _composer_ground_blocks()


def _composer_data_ground_blocks() -> set:
    """The OTHER ground mechanism: templates whose fn calls `_data_ground()` (LAYER-3 ambient ground
    + legibility veil). Same authored field, same real pixels — a different helper."""
    src = (BRIDGE / "compose.py").read_text(encoding="utf-8")
    reg = re.search(r"^BLOCKS = \{(.*?)\n?\}", src, re.S | re.M)
    registry = dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1)))
    bounds = [(m.start(), m.group(1)) for m in re.finditer(r"^def (\w+)\(", src, re.M)] + [(len(src), "")]
    consuming = set()
    for i in range(len(bounds) - 1):
        fn = bounds[i][1]
        if fn != "_data_ground" and "_data_ground(" in src[bounds[i][0]:bounds[i + 1][0]]:
            consuming.add(fn)
    return {t for t, fn in registry.items() if fn in consuming}


def test_data_ground_registry_matches_the_composer():
    from nolan.block_registry import DATA_GROUND_BLOCKS
    assert set(DATA_GROUND_BLOCKS) == _composer_data_ground_blocks()


def test_consumes_ground_helper_agrees():
    from nolan.block_registry import ANY_GROUND_BLOCKS, consumes_ground
    assert consumes_ground("statement") and consumes_ground("pull_quote")
    assert consumes_ground("chart") and consumes_ground("isotype")   # via _data_ground
    assert not consumes_ground("hero") and not consumes_ground("lower_third")
    assert all(consumes_ground(b) for b in ANY_GROUND_BLOCKS)


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
    # autoground places media only on the `media_ground` six (an ambient ground behind data is an
    # editorial choice, not a pre-pass's); metrics must CREDIT both mechanisms, so it reads the union.
    for rel, name in (("hyperframes/autoground.py", "GROUND_BLOCKS"),
                      ("style_contract/metrics.py", "ANY_GROUND_BLOCKS")):
        text = (SRC / rel).read_text(encoding="utf-8")
        assert f"block_registry import {name}" in text, f"{rel} must read the shared registry ({name})"


# --- phantom reveal cues (postmortem item 4) --------------------------------------------------

def _composer_cue_blocks() -> set:
    """Re-derive: registered templates whose composer reads the author-supplied `at`."""
    import re
    src, registry = {}, {}
    for name in ("compose.py",):          # ONE composer since the 2026-07-26 extension merge
        src[name] = (BRIDGE / name).read_text(encoding="utf-8")
        reg = re.search(r"^BLOCKS = \{(.*?)\n?\}", src[name], re.S | re.M)
        registry.update(dict(re.findall(r'"(\w+)":\s*(\w+)', reg.group(1))))

    def body(fn):
        for s in src.values():
            i = s.find(f"def {fn}(")
            if i < 0:
                continue
            j = s.find("\ndef ", i + 1)
            return s[i:j if j > 0 else len(s)]
        return ""

    # `_reveal_cues(` is the ONLY thing that reads an author `at`; a bare `_reveal_times(` does not.
    # It used to count, and five blocks (data_table, histogram, layout, process, small_multiples) called
    # `_reveal_times(n, start, dur, [None] * n)` — scheduled, but deaf to every anchor. The registry
    # therefore claimed cue support they lacked, and `author.py`, which gates on this set, ACCEPTED an
    # `at` that could never fire: the phantom-field class, hiding behind an honesty test whose predicate
    # was looser than the claim it was checking. They read cues now; the predicate no longer lets a
    # future block back into the set for free.
    reads = re.compile(r"""get\(\s*["']at["']|\[["']at["']\]|_reveal_cues\(""")
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


def test_an_sfx_cue_is_not_a_reveal_cue():
    """INCIDENT (cold-agent batch on homer-hf): `data.sfx[].at` is an SFX cue time — written by
    hyperframes/sfx_design.py, read by hyperframes/sound.py — but the cue walker matched ANY numeric
    `at` anywhere in a scene's data, so on a `statement` the gate rejected the whole spec as carrying
    an INERT reveal cue.

    What it cost was not the false alarm: three unrelated proposals (an eyebrow, an asset swap) were
    HARD-REFUSED because of a pre-existing field the agent never touched. WIRING_CHECKLIST #11 — a
    check whose failures are false positives takes its true positives with it."""
    from nolan.block_registry import find_cue_fields
    sfx = {"lines": ["x"], "sfx": [{"cue": "whoosh", "at": 2.4, "why": "transition"}]}
    assert find_cue_fields(sfx) == [], "an SFX cue is not an element reveal"


def test_a_camera_arrival_time_is_not_a_reveal_cue():
    """`ground.at` is when the camera MOVE arrives, per the camera schema — a different clock again."""
    from nolan.block_registry import find_cue_fields
    assert find_cue_fields({"ground": {"kind": "image", "src": "a.jpg", "at": 1.5}}) == []


def test_real_reveal_cues_are_still_found():
    """The gate must keep catching what it exists for: a phantom `at` on a block that ignores it."""
    from nolan.block_registry import find_cue_fields
    assert find_cue_fields({"events": [{"year": 1, "at": 3.0}]}) == ["data.events[0].at"]
    assert find_cue_fields({"items": [{"label": "a"}, {"label": "b", "at": 2.0}]}) == ["data.items[1].at"]


def test_a_statement_carrying_sfx_still_validates():
    """End to end: the exact spec shape that blocked three homer proposals."""
    import json
    import subprocess
    import sys
    import tempfile
    scene = {"id": "s2", "type": "statement", "start": 0, "dur": 5,
             "data": {"lines": ["there is only one problem"],
                      "sfx": [{"cue": "whoosh", "at": 0.3, "why": "beat turn"}]}}
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "s.json"
        f.write_text(json.dumps({"frames": [{"id": "f1", "dur": 8.0, "scenes": [scene]}]}), encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", str(BRIDGE / "author.py"),
                            "--spec", str(f), "--validate-only"],
                           cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    assert r.returncode == 0, f"a statement with SFX must validate:\n{r.stdout}{r.stderr}"
