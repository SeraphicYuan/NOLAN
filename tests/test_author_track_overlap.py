"""Same-track time overlap is LEGAL in a composed frame. Do not gate on it — this is attempt #3.

Postmortem item 5 asked for `assemble-index.mjs`'s track-overlap check to run at author time instead of
minutes later at render, citing a centred `spotlight` that emitted both halves of its label on one track
over one window: "so NO centred spotlight had ever assembled". Every part of that premise was checked
and every part is false:

  1. NO ASSEMBLER HAS THE CHECK. All four `assemble-index.mjs` copies in the repo (hf-author,
     music-to-video, pr-to-video, product-launch-video) contain zero track-overlap logic. The claim
     traces to a COMMENT in two of them — "Track lanes (same-track time-overlap is illegal — lint
     timeline_track_too_dense)" — which describes the top-level INDEX (frame sub-comps on lane 1,
     captions on lane 2, voice on 10, bgm on 11), not the tracks inside a frame's own composition.
  2. THE RULE IT NAMES IS A DIFFERENT RULE. `timeline_track_too_dense` is a DENSITY warning about too
     many clips on one timeline (the fix it suggests is chunking into sub-compositions), not a
     prohibition on two clips sharing a moment.
  3. THE PRE-FIX ARTIFACT RENDERED, CORRECTLY. `videos/_stress_spotlight` still carries the exact
     pre-fix HTML — `s1-labl` and `s1-labr`, both `data-track-index="2"`, both 0.0-6.0 — and it has a
     finished `renders/_stress_spotlight.mp4`. A frame pulled from it shows BOTH label halves painted
     either side of the subject. The centred spotlight had assembled all along.
     `the-openai-debate` likewise shipped with 10 same-scene same-track collisions in its `raw` scenes.

Attempt #1 gated on raw same-track overlap and broke 13 tests: adjacent scenes overlap BY DESIGN,
because the composer gives each a ~0.6s tail (scenes at 0/5/10 emit 0-5.60, 5.00-10.60, 10.00-14.00)
and the transitions injector ping-pongs the lanes afterwards. Attempt #2 (this file's previous version)
proposed scoping to same-scene identical windows, which is exactly the shape the evidence above proves
legal. There is no rule at this door to enforce, so nothing is enforced here.

What was real in item 5 is the general principle — a composer bug is cheapest in the composer's own
gate — and it is already served by the phantom-cue gate and the layout lint, which check rules that
demonstrably exist.
"""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"


def test_author_does_not_gate_on_track_overlap():
    """The assertion that stops attempt #4. If you are here because you want to add this check, read
    the module docstring first: the artifact that 'could never assemble' is sitting in videos/ with a
    rendered mp4 next to it."""
    src = (BRIDGE / "author.py").read_text(encoding="utf-8")
    build = src[src.index('for fr in spec["frames"]:'):]
    for token in ("track_overlaps", "scene_track_collisions", "data-track-index"):
        assert token not in build, f"author.py gates on {token} — see this file's docstring"


def test_the_composer_still_emits_a_centred_spotlight_on_two_lanes():
    """The lane split shipped in 90ab2f1 is KEPT — it gives the two halves a deterministic z-order and
    costs nothing — but it is not load-bearing, and its original justification was the false premise
    above. Pinned so the behaviour is documented rather than folklore."""
    import re
    sys.path.insert(0, str(BRIDGE))
    try:
        import compose            # spotlight lives here since the 2026-07-26 extension merge
    finally:
        sys.path.pop(0)
    sc = {"id": "s1", "start": 0.0, "dur": 6.0,
          "data": {"subject": "assets/x.png", "position": "center", "words": "left right"}}
    frag, _tl = compose.spotlight("s1", sc)
    lanes = {}
    for tag in re.findall(r'<[a-z]+ id="s1-lab[lr]"[^>]*>', "".join(frag)):
        half = re.search(r'id="s1-(lab[lr])"', tag).group(1)
        lanes[half] = re.search(r'data-track-index="(\d+)"', tag).group(1)
    assert len(lanes) == 2, lanes              # a centred spotlight paints BOTH halves
    assert lanes["labl"] != lanes["labr"], lanes
