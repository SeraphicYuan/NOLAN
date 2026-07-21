"""Reveal-CHARACTER registry — the small pool of entrance PERSONALITIES a data reveal can take.

The reveal SCHEDULER (compose._reveal_times) owns WHEN a reveal fires; a CHARACTER owns HOW — the ease
curve + how long the motion breathes. Meaning picks it: a shock number SNAPS, a climbing trend BUILDs, a
punchline STAMPs, ambient data DRIFTs, most things SETTLE.

This module is the SINGLE SOURCE OF TRUTH for the pool:
  - compose.py consumes it in EVERY data-viz block, via ease(id) + dur_scale(id) (the executor);
  - catalog.json mirrors it (check_catalog enforces registry↔catalog parity);
  - author.py validates the authored `data.reveal_char` against it AND suggests a fitting character;
  - check_reveal_sync proves the field actually changes the reveal (not a phantom).

Authored per DATA scene as `data.reveal_char` (distinct from `data.reveal`, the per-LETTER text style).
Adding a character = one entry here → it auto-appears in the catalog + the parity test guards it.
"""

DEFAULT = "settle"

REVEAL_CHARS = {
    "settle": {"ease": "back.out(1.2)", "dur_scale": 1.0,
               "purpose": "a confident, lightly-overshooting land — the default voice of a data reveal",
               "when_to_use": "most reveals; a value arriving with quiet authority",
               "not_for": "a hard shock (snap) or a slow trend (build)"},
    "snap": {"ease": "power4.out", "dur_scale": 0.6,
             "purpose": "a hard, fast arrival with no overshoot — it just SLAMS into place",
             "when_to_use": "a stark or shocking single number the narration hits hard",
             "not_for": "many elements in sequence or a gentle trend (reads aggressive)"},
    "build": {"ease": "power1.inOut", "dur_scale": 1.5,
              "purpose": "a slow, even accumulation that runs the length of its beat",
              "when_to_use": "a trend climbing, a cumulative total, a value that GROWS as the point develops",
              "not_for": "a punchy callout (use snap/stamp)"},
    "drift": {"ease": "sine.inOut", "dur_scale": 1.25,
              "purpose": "a soft, atmospheric fade — barely-there motion",
              "when_to_use": "ambient / contextual data sitting under narration; a calm mood",
              "not_for": "the emphatic number a beat lands on (too weak)"},
    "stamp": {"ease": "back.out(2.6)", "dur_scale": 0.75,
              "purpose": "an emphatic pop with strong overshoot — a visual exclamation mark",
              "when_to_use": "a punchline figure, a reveal the VO leans on",
              "not_for": "subtle or many-element reveals (too bouncy)"},
}


def ids():
    return list(REVEAL_CHARS)


def is_valid(cid):
    return cid in REVEAL_CHARS


def resolve(cid):
    """The registry entry for a character id; the default ('settle') for unknown/None (the gate warns; the
    executor never crashes)."""
    return REVEAL_CHARS.get(cid, REVEAL_CHARS[DEFAULT])


def ease(cid):
    """The GSAP ease string for a reveal character — drop into a reveal tween's `ease:`."""
    return resolve(cid)["ease"]


def dur_scale(cid):
    """The duration multiplier for a reveal character — a `snap` runs shorter, a `build` longer."""
    return resolve(cid)["dur_scale"]


def _elements(d):
    """The largest authored list-of-dicts in a data block (its reveal elements) — field-name-agnostic."""
    best = []
    for v in (d or {}).values():
        if isinstance(v, list) and len(v) > len(best) and any(isinstance(x, dict) for x in v):
            best = v
    return best


def suggest(sc):
    """A heuristic reveal-character SUGGESTION for a data scene (an authoring ASSIST — the author can accept
    or override). Maps MEANING → motion:
      - a cumulative / trend shape (line or waterfall chart) → `build` (it grows as the point develops);
      - ONE stark number (a single-element stat/scale/chart) → `snap` (it should slam);
      - a highlighted punchline element (`hl`) on a small block → `stamp`;
      - a many-element (>6) block → `drift` (ambient, don't over-bounce a crowd);
      - else `settle`.
    Returns a character id; never raises."""
    t = sc.get("type")
    d = sc.get("data", {}) or {}
    els = _elements(d)
    n = len(els)
    if t == "chart" and d.get("type") in ("line", "waterfall"):
        return "build"
    if t in ("stat", "scale", "chart", "pie") and n == 1:
        return "snap"
    if n and n <= 3 and any(isinstance(e, dict) and e.get("hl") for e in els):
        return "stamp"
    if n > 6:
        return "drift"
    return DEFAULT
