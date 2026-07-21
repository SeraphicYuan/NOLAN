"""Honesty test for the REVEAL-SYNC contract (see AUTHOR_PROMPT.md "Reveal timing" + the module
contract in CLAUDE.md / docs/WIRING_CHECKLIST.md).

The rule: a DATA/element block must schedule its per-element reveals through the SHARED reveal
scheduler (`_reveal_times` / `_reveal_dur` / `_reveal_cues`) so every reveal (a) spreads across the
block's full window instead of front-loading in ~2s, and (b) can be pulled onto narration time by the
aligner (each element's `_cue`). A hardcoded incremental stagger — `cue = start + LEAD + i*STEP` — is
the anti-pattern that made data blocks read stale (reveal all content in 2s, then hold frozen for 10s
while numbers pop before the VO says them). This test fails if a NEW hardcoded stagger appears in
compose.py outside the small allowlist of legitimate non-data cadences (text-line reads, layout
entrances, cosmetic label cascades), so a future block-builder can't silently reintroduce it.

Run:  python -X utf8 check_reveal_sync.py
Exits 1 on any un-allowlisted hardcoded reveal stagger, or if the shared scheduler has gone unused."""
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE / "compose.py").read_text(encoding="utf-8")
LINES = SRC.splitlines()

# A hardcoded incremental reveal cue: `start + <float> + <idx> * <float>`  (any spacing / index name).
PAT = re.compile(r"start\s*\+\s*[\d.]+\s*\+\s*[a-zA-Z_]\w*\s*\*\s*[\d.]+")

# Functions whose per-line/per-cell stagger is a DELIBERATE reading/entrance cadence, NOT a data reveal
# that must track narration. Keep this list SHORT and justified — adding a data block here defeats the
# whole contract. (Verified 2026-07-20: text-line reveals, gallery/carousel entrance, axis-label cascade,
# chat dialogue beats.)
ALLOW = {
    "_line_times":     "text LINE scheduler — VO-syncs each line to data._line_cues (aligner) via "
                       "_reveal_times; the start+i*step here is only the PRE-SYNC preview fallback",
    "hero":            "hero / asymmetric-hero title lines — text entrance, reading cadence",
    "document":        "document block paragraphs — reading cadence (a page you read down)",
    "code":            "code line cascade (0.045s) — cosmetic typing feel",
    "carousel":        "carousel/card-focus layout entrance — cosmetic arrangement, not a data reveal",
    "chat_thread":     "chat message beats — deliberate dialogue pacing",
    "_cmp_text":       "comparison / juxtaposition text-side lines — reading cadence",
    "_panel_content":  "comparison panel text lines — reading cadence",
}


def _enclosing_fn(lineno):
    """Return the name of the innermost `def` whose body contains 1-indexed `lineno`."""
    tree = ast.parse(SRC)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= lineno <= end:
                if best is None or node.lineno > best.lineno:  # innermost
                    best = node
    return best.name if best else "<module>"


def main():
    violations = []
    for i, line in enumerate(LINES, 1):
        if line.lstrip().startswith("#"):
            continue
        if PAT.search(line):
            fn = _enclosing_fn(i)
            if fn not in ALLOW:
                violations.append((i, fn, line.strip()))

    # the shared scheduler must actually be in use (guards against someone deleting it)
    if "_reveal_times" not in SRC:
        violations.append((0, "<module>", "shared reveal scheduler _reveal_times is MISSING from compose.py"))

    if violations:
        print("REVEAL-SYNC VIOLATION — data/element reveals must use the shared scheduler")
        print("(_reveal_times / _reveal_dur / _reveal_cues), not a hardcoded `start + LEAD + i*STEP`.")
        print("See AUTHOR_PROMPT.md 'Reveal timing' + docs/WIRING_CHECKLIST.md.\n")
        for ln, fn, txt in violations:
            print(f"  ✗ compose.py:{ln}  in {fn}()")
            print(f"      {txt[:110]}")
        print("\nFix: schedule reveals with `times = _reveal_times(len(items), start, dur, "
              "_reveal_cues(items, start))` and set each element's cue to `times[i]` (scale its "
              "count-up/draw duration with `_reveal_dur(times, i, start, dur)`).")
        print("If this IS a deliberate reading/entrance cadence (not a data reveal), add the function "
              "to check_reveal_sync.ALLOW with a one-line justification.")
        sys.exit(1)

    # data-ground invariant: a grounded data-viz block must emit AT MOST ONE clip per track lane in its
    # ground (else assemble-index rejects the frame for same-track time-overlap — the media_ground scrim +
    # a second veil bug). Runtime-check the composer directly.
    import compose as _c
    for kind, gnd in (("image", {"kind": "image", "src": "assets/x.jpg", "kenburns": [1.0, 1.12], "dim": 0.6}),
                      ("paper", {"kind": "paper"})):
        sc = {"id": "g1", "type": "chart", "start": 0, "dur": 12,
              "data": {"type": "bar", "series": [{"label": "A", "value": 10}, {"label": "B", "value": 20}], "ground": gnd}}
        html = str(_c.BLOCKS["chart"]("g1", sc))
        for lane in ("0", "1"):
            n = html.count(f'data-track-index="{lane}"')
            if n > 1:
                print(f"DATA-GROUND VIOLATION — {kind} ground emits {n} clips on track {lane} (must be ≤1); "
                      f"assemble-index will reject the frame for same-track overlap. See compose._data_ground.")
                sys.exit(1)

    # reveal-CHARACTER consumption: `data.reveal_char` must actually change the reveal (ease/duration),
    # else it's a phantom authored field. Render a chart with two distinct characters and require the
    # emitted bar tween to differ.
    def _bar_tween(char):
        sc = {"id": "rc", "type": "chart", "start": 0, "dur": 12,
              "data": {"type": "bar", "series": [{"label": "A", "value": 10}, {"label": "B", "value": 20}],
                       **({"reveal_char": char} if char else {})}}
        m = re.search(r'-b0"[^;]*?duration:([0-9.]+),ease:"([^"]+)"', str(_c.BLOCKS["chart"]("rc", sc)))
        return (m.group(2), m.group(1)) if m else (None, None)
    snap, build = _bar_tween("snap"), _bar_tween("build")
    if snap == (None, None) or snap == build:
        print("REVEAL-CHARACTER PHANTOM — `data.reveal_char` does not change the reveal (ease/duration "
              f"identical for snap vs build: {snap} == {build}). The character registry is authored but not "
              "consumed. Wire it via _reveal_ease(d) + _reveal_dur(..., d=d) in the block's reveal tween.")
        sys.exit(1)
    if "_reveal_ease(" not in SRC:
        print("REVEAL-CHARACTER UNUSED — no block calls _reveal_ease(); the character registry is dead.")
        sys.exit(1)

    # A-P2.5 time-series playhead: a line chart with data.playhead emits a sweeping time-cursor tween.
    ph = str(_c.BLOCKS["chart"]("ph", {"id": "ph", "type": "chart", "start": 0, "dur": 12,
             "data": {"type": "line", "playhead": True,
                      "series": [{"label": "a", "value": 1}, {"label": "b", "value": 3}]}}))
    if "-ph" not in ph or 'to("#ph-ph"' not in ph:
        print("PLAYHEAD MISSING — a line chart with data.playhead does not emit the sweeping time-cursor. "
              "See compose.chart (typ == 'line', d.get('playhead')).")
        sys.exit(1)

    used = len(re.findall(r"_reveal_times\(", SRC))
    nchar = len(re.findall(r"_reveal_ease\(", SRC))
    print(f"OK — reveal-sync contract holds. Shared scheduler used at {used} sites; reveal-character applied "
          f"at {nchar} sites ({len(getattr(_c, 'REVEAL_CHARS', {}))} characters); "
          f"{len(ALLOW)} allow-listed non-data cadences; data-ground single-lane invariant holds.")


if __name__ == "__main__":
    main()
