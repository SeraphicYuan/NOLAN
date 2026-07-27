"""Does every block LISTEN to narration? Asked of the block, not of its source.

`check_reveal_sync.py` guards the other half of this contract — that a data block schedules its
per-element reveals through the shared scheduler instead of a hardcoded `start + LEAD + i*STEP`. It is
a SYNTACTIC test, and that is exactly why it never caught the defect this file exists for: `pull_quote`
revealed its whole quote at `start + 0.5`, a single literal, which matches no stagger pattern. It
passed cleanly while being deaf by construction, and diamond-v3 3:41 shipped a 13-word quote fully on
screen ~3.7s before the narration reached it.

Static analysis cannot answer the question either. A scheduled reveal reads `{t:.2f}` where
`t = times[i]`; a hardcoded one reads `{start+0.5}`. Both are "an f-string with a number in it", and a
first pass at this audit wrongly cleared `timeline` on exactly that basis (it contains zero references
to the cue system).

So ASK THE BLOCK. Compose it twice — once plain, once with narration cues injected — and diff the
timeline it emits. A block whose output does not move is not listening, whatever its source looks like.

The three cue surfaces a block can read, all resolved by `nolan.hyperframes.sync`:
    `_cue`          per ELEMENT   (list-of-dicts: chart series, stat items, table rows …)
    `_line_cues`    per LINE      (`data.lines`)
    `_field_cues`   per FIELD     (`data.quote` / `title` / `caption` … — sync.PROSE_FIELDS)
"""
import json
import re
import sys
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

from nolan.hyperframes import sync  # noqa: E402

CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))["scene_templates"]

# Blocks whose cadence is DELIBERATE, not a data reveal. Keep this list short and justified — adding a
# content block here defeats the contract, which is the same rule check_reveal_sync.ALLOW carries.
DELIBERATE_CADENCE = {
    "bar_race":    "a race IS the passage of time — its bars are driven by the clock, not by a phrase",
    "chat_thread": "dialogue beats: messages land in conversational rhythm, deliberately",
    "collage":     "an arrangement entrance — the subjects assemble as one gesture",
    "hero":        "title-card entrance cadence (also allow-listed in check_reveal_sync)",
    "lower_third": "a name/role lower-third is design copy, not narration",
    "spotlight":   "effect labels on a reel-look treatment — kinetic copy, not spoken prose",
    "stream":      "a stream graph is ONE continuous wipe across its own x-axis; its title is static "
                   "furniture, so there is no per-element reveal for narration to move",
    "raw":         "an authored raw scene owns its own timeline by definition",
}

# Shapes the schema text cannot produce on its own.
FIXTURES = {
    # rows as DICTS — the anchorable form. A row given as a bare array still spreads across the window
    # (layer 1), it just cannot be pinned to a word: there is nowhere on an array to write `_cue`, and a
    # dataset-bound table usually has no narration per row to pin it to anyway.
    "data_table": {"title": "a spoken phrase here", "columns": ["one", "two"],
                   "rows": [{"one": "a", "two": "b"}, {"one": "c", "two": "d"}]},
    "quadrant": {"x": {"label": "x axis"}, "y": {"label": "y axis"},
                 "items": [{"x": 0.2, "y": 0.3, "label": "alpha one"},
                           {"x": 0.7, "y": 0.8, "label": "beta two"}]},
    "sankey": {"source": {"label": "the total", "value": 100},
               "targets": [{"label": "alpha one", "value": 60}, {"label": "beta two", "value": 40}]},
    "spans": {"spans": [{"label": "alpha one", "start": 0, "end": 5},
                        {"label": "beta two", "start": 5, "end": 9}]},
    "split_view": {"paper": {"document": "doc.pdf"},
                   "right": {"kind": "text", "title": "a spoken phrase here",
                             "lines": ["the first spoken line", "the second spoken line"]}},
    "stream": {"x": ["t1", "t2", "t3"],
               "series": [{"label": "alpha one", "values": [1, 2, 3]},
                          {"label": "beta two", "values": [3, 2, 1]}]},
    "linedraw": {"paths": ["M0 0 L100 100"], "viewBox": "0 0 100 100",
                 "lead": "a spoken phrase here now"},
    "carousel": {"title": "a spoken phrase here",
                 "images": [{"src": "a.jpg", "caption": "alpha one here"},
                            {"src": "b.jpg", "caption": "beta two here"}]},
    "gallery": {"title": "a spoken phrase here",
                "images": [{"src": "a.jpg", "caption": "alpha one here"},
                           {"src": "b.jpg", "caption": "beta two here"}]},
    "comparison": {"title": "a spoken phrase here",
                   "left": {"kind": "text", "title": "the left side", "lines": ["left line one"]},
                   "right": {"kind": "text", "title": "the right side", "lines": ["right line one"]}},
    "juxtaposition": {"title": "a spoken phrase here",
                      "left": {"kind": "text", "title": "the left side", "lines": ["left line one"]},
                      "right": {"kind": "text", "title": "the right side", "lines": ["right line one"]}},
    "spectrum": {"title": "a spoken phrase here", "axis": {"lo": "cold", "hi": "hot"},
                 "items": [{"label": "alpha one", "value": 0.2},
                           {"label": "beta two", "value": 0.8}]},
    "diagram": {"title": "a spoken phrase here",
                "nodes": [{"id": "a", "label": "alpha one"}, {"id": "b", "label": "beta two"}],
                "edges": [{"from": "a", "to": "b"}]},
    "document": {"title": "a spoken phrase here", "source": "doc.pdf",
                 "annotations": [{"text": "alpha one here", "rect": [0.1, 0.1, 0.3, 0.2]}]},
    "newshead": {"headline": "a spoken headline here", "caption": "a spoken caption here",
                 "subhead": "a spoken subhead here", "date": "1889", "image": "a.jpg"},
    "stat": {"items": [{"value": 10, "label": "alpha one here"},
                       {"value": 20, "label": "beta two here"}]},
    "statement": {"lines": ["the first spoken line here", "the second spoken line here"],
                  "operative": "spoken"},
}


def _synth(bt):
    """Plausible data for a block from its declared schema — the catalog is in-repo, so this test is
    self-contained (it must not need any user project on disk)."""
    if bt in FIXTURES:
        return dict(FIXTURES[bt])
    sch = (CATALOG.get(bt) or {}).get("data_schema") or {}
    d = {}
    for k, v in sch.items():
        vt = str(v).lower()
        if k in ("ground", "register", "kicker", "dataset", "query", "encode"):
            continue
        if k == "lines":
            d[k] = ["the first spoken line here", "the second spoken line here"]
        elif "array" in vt or k in ("items", "series", "rows", "steps", "nodes", "columns",
                                    "points", "bins", "events", "callouts", "images", "subjects"):
            d[k] = [{"label": "alpha one", "value": 10, "text": "alpha one"},
                    {"label": "beta two", "value": 20, "text": "beta two"}]
        elif "number" in vt or "int" in vt or "float" in vt:
            d[k] = 12
        elif "bool" in vt:
            d[k] = False
        else:
            d[k] = "a spoken phrase here"
    return d


_TIME = re.compile(r",\s*(-?\d+(?:\.\d+)?)\s*\)\s*;")


def _timeline(bt, sc):
    out = compose.BLOCKS[bt](sc["id"], sc)
    s = out if isinstance(out, str) else json.dumps(out)
    return sorted(round(float(x), 2) for x in _TIME.findall(s))


def _inject(data, base=0.0):
    """Write a cue into every surface this block's data can express. Returns how many."""
    n = 0
    for k, v in list(data.items()):
        if isinstance(v, list) and any(isinstance(x, dict) for x in v):
            for i, el in enumerate(v):
                if isinstance(el, dict):
                    el["_cue"] = round(base + 7.0 + i * 0.5, 3)
                    n += 1
        if k == "lines" and isinstance(v, list) and v:
            data["_line_cues"] = [round(base + 7.0 + i * 0.5, 3) for i in range(len(v))]
            n += 1
    fields = {f: round(base + 7.0, 3) for f in sync.PROSE_FIELDS
              if isinstance(data.get(f), str) and len(data[f].split()) >= sync._PROSE_MIN_WORDS}
    if fields:
        data["_field_cues"] = fields
        n += len(fields)
    # …and one level down, exactly where `sync._retime_panels` writes. A two-sided block keeps its prose
    # under `left`/`right`/`paper`, and an injector that only walks the top level would report the
    # block deaf when it is the TEST that is not looking.
    for k in sync._PANEL_KEYS:
        side = data.get(k)
        if isinstance(side, dict):
            if isinstance(side.get("title"), list) and side["title"]:
                side["_line_cues"] = [round(base + 7.0 + i * 0.4, 3) for i in range(len(side["title"]))]
                n += 1
            n += _inject(side, base)
    return n


def _scene(bt):
    return {"id": "s1", "type": bt, "start": 0.0, "dur": 14.0, "data": _synth(bt)}


@pytest.mark.parametrize("bt", sorted(b for b in compose.BLOCKS if b not in DELIBERATE_CADENCE))
def test_the_block_moves_its_reveals_onto_the_spoken_word(bt):
    """Inject narration cues; the emitted timeline must change. If it does not, the aligner's answer is
    being computed and thrown away — the phantom-field class, one layer down."""
    plain = _scene(bt)
    try:
        before = _timeline(bt, json.loads(json.dumps(plain)))
    except Exception as e:                      # a fixture this test could not synthesize
        pytest.skip(f"{bt}: no usable fixture ({type(e).__name__}: {e})")
    cued = json.loads(json.dumps(plain))
    n = _inject(cued["data"])
    assert n, (f"{bt} exposes NO cue surface at all — nothing in its data can carry a narration time, "
               f"so sync cannot pin it even in principle. Give it an element list, `lines`, or a field "
               f"named in sync.PROSE_FIELDS.")
    after = _timeline(bt, cued)
    assert before != after, (
        f"{bt} IGNORES the narration cues sync writes for it ({n} cue slots). Its reveals are on a wall "
        f"clock, so the visual cannot track the voice. Read them via `_reveal_cues(items, start)` for "
        f"elements, `data._line_cues` for lines, or `_prose_cue(d, field, start)` for a prose field.")


def test_the_deliberate_cadences_are_declared_and_still_real():
    """An allowlist nobody prunes becomes a place to hide. Every entry must still be a real block."""
    unknown = sorted(set(DELIBERATE_CADENCE) - set(compose.BLOCKS))
    assert not unknown, f"allow-listed blocks that no longer exist: {unknown}"
    for bt, why in DELIBERATE_CADENCE.items():
        assert len(why) > 25, f"{bt}: a one-word justification is not a justification"


def test_coverage_is_reported_not_assumed():
    """No silent caps: this test states how much of the block arsenal it actually exercises."""
    total = len(compose.BLOCKS)
    skipped = []
    for bt in sorted(compose.BLOCKS):
        if bt in DELIBERATE_CADENCE:
            continue
        try:
            _timeline(bt, _scene(bt))
        except Exception:
            skipped.append(bt)
    covered = total - len(DELIBERATE_CADENCE) - len(skipped)
    assert covered >= 40, (f"only {covered}/{total} blocks are exercised — fixtures missing for "
                           f"{skipped}. Add them to FIXTURES rather than letting coverage rot.")


def test_prose_fields_resolve_to_the_spoken_time():
    """Layer 3 end to end: a quote resolves to the moment its words are said, a title is only NUDGED.

    The hold policy is the load-bearing half. A quote is the beat's payload and may wait as long as the
    narration takes; a title is the frame's anchor, and parking it 6s in trades a lead for a hole.
    """
    from nolan.whisper import WordTimestamp
    toks = ("we open on something else entirely and then he said the only way to increase the value "
            "is to make them scarce").split()
    words = [WordTimestamp(w, float(i), float(i) + 0.9) for i, w in enumerate(toks)]
    quote = "the only way to increase the value is to make them scarce"
    spoken = float(toks.index("the", toks.index("said")))

    sc = {"start": 0.0, "dur": 20.0}
    d = {"quote": quote}
    assert sync._retime_prose(sc, d, words) == 1
    assert abs(d["_field_cues"]["quote"] - spoken) < 0.01, d["_field_cues"]

    # the same text as a TITLE is beyond a title's hold bound (0.35 * 20s = 7s) → left unpinned
    d2 = {"title": quote}
    sync._retime_prose(sc, d2, words)
    assert "title" not in (d2.get("_field_cues") or {}), \
        "a title parked past its hold bound leaves the frame headless"

    # …and inside the bound it IS pinned
    d3 = {"title": quote}
    sync._retime_prose({"start": 0.0, "dur": 60.0}, d3, words)
    assert abs(d3["_field_cues"]["title"] - spoken) < 0.01

    # idempotent: removing the text un-pins it
    d4 = dict(d)
    d4.pop("quote")
    sync._retime_prose(sc, d4, words)
    assert not d4.get("_field_cues")


def test_the_kicker_is_still_never_prose():
    """Design copy must not drive placement — the 12:23 lead and the 17s drag both came from that."""
    assert "kicker" not in sync.PROSE_FIELDS
