"""Test: script-style extraction sampling keeps both ends of long transcripts.

Guards the fix for the Stage-B truncation bug where `text[:max_chars]` silently
dropped every transcript's ending — so the `closing`/`narrative_structure`
fields were extracted from a transcript the model never saw the end of.

Usage:
    D:/env/nolan/python.exe scripts/test_script_style_extraction.py
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.webui.operations import _sample_for_extraction, analyze_style


def main():
    # A transcript with a distinctive HEAD and TAIL and filler in the middle.
    head = "HOOK: We need to talk about the opening. "
    tail = " CLOSING: thanks for watching, take care. END."
    body = head + ("middle filler. " * 5000) + tail
    assert len(body) > 20000, "fixture must overflow a realistic cap"

    cap = 4000
    out = _sample_for_extraction(body, cap)

    # 1. Never exceeds the cap.
    assert len(out) <= cap, f"output {len(out)} > cap {cap}"
    # 2. Both ends survive — this is the whole point of the fix.
    assert head in out, "opening was dropped"
    assert tail in out, "closing was dropped (regression: head-only truncation)"
    assert "trimmed for length" in out, "expected elision marker between ends"
    # 3. Head-heavy split (~60/40): more head chars than tail chars kept.
    marker_i = out.index("[…transcript trimmed")
    head_part, tail_part = out[:marker_i], out[out.index("\n\n", marker_i + 1):]
    assert len(head_part) > len(tail_part), "head should get the larger share"
    print(f"long transcript: head+tail preserved, len={len(out)} <= {cap} OK")

    # 4. Under-cap and no-cap pass through untouched.
    assert _sample_for_extraction("short", 4000) == "short"
    assert _sample_for_extraction(body, 0) == body, "max_chars<=0 = no cap"
    assert _sample_for_extraction(body, len(body)) == body, "exact fit untouched"
    print("under-cap / no-cap pass-through OK")

    # 5. Degenerate cap smaller than the marker degrades to a head slice safely.
    tiny = _sample_for_extraction(body, 5)
    assert len(tiny) <= 5 and tiny == body[:5]
    print("degenerate tiny-cap OK")

    # 6. Regression guard: the default cap is no longer the miscalibrated 20k.
    default_cap = inspect.signature(analyze_style).parameters["extract_max_chars"].default
    assert default_cap >= 100000, f"default cap too low again: {default_cap}"
    print(f"default extract_max_chars = {default_cap} OK")

    print("\nOK - extraction sampling verified.")


if __name__ == "__main__":
    main()
