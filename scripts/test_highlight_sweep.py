"""Test: animated highlight-marker sweep (Underline style="highlight").

Verifies:
  1. The highlight bar actually renders (composites onto the frame).
  2. The swept area grows monotonically with progress.
  3. Phrase-based selection (highlight_text) highlights only the matched span,
     i.e. strictly fewer pixels than sweeping the whole element.

Usage:
    D:/env/nolan/python.exe scripts/test_highlight_sweep.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.base import BaseRenderer, Element
from src.nolan.renderer.effects import Underline, EffectPresets
from src.nolan.renderer.scenes.document_highlight import DocumentHighlightRenderer

TEXT = ("From 2019 through 2024, the Low-Wage 100 spent $644 billion on "
        "stock buybacks.")
PHRASE = "From 2019 through 2024"
FONT = "C:/Windows/Fonts/arialbd.ttf"


def build(highlight=True, highlight_text=PHRASE):
    r = BaseRenderer(width=640, height=360, fps=30, bg_color=(18, 18, 24))
    r.timeline.duration = 7.0
    el = Element(
        id="text", element_type="text", text=TEXT, font_path=FONT,
        font_size=26, color=(235, 235, 240), x="center", y="center",
        max_width=560, max_lines=4, text_align="left",
    )
    if highlight:
        el.add_effect(Underline(
            style="highlight", highlight_text=highlight_text,
            color=(235, 235, 240), opacity=0.5, start=1.0, duration=3.0,
        ))
    r.add_element(el)
    return r


def changed_pixels(frame, baseline):
    return int(np.any(frame != baseline, axis=2).sum())


def main():
    # Baseline: identical scene, no highlight.
    base = build(highlight=False)

    # 1 + 2: phrase sweep grows monotonically.
    phrase = build(highlight=True, highlight_text=PHRASE)
    counts = []
    for t in (1.2, 2.5, 4.5):  # progress ~0.07, ~0.5, 1.0 (after fade-in)
        b = base.render_frame(t)
        f = phrase.render_frame(t)
        counts.append(changed_pixels(f, b))
    print(f"phrase changed pixels by progress: {counts}")
    assert counts[0] < counts[1] < counts[2], f"not monotonic: {counts}"
    assert counts[0] > 0, "highlight never rendered (still a stub?)"

    # 3: phrase span is a strict subset of the whole-element sweep.
    whole = build(highlight=True, highlight_text=None)
    t = 4.5  # full progress
    b = base.render_frame(t)
    phrase_n = changed_pixels(phrase.render_frame(t), b)
    whole_n = changed_pixels(whole.render_frame(t), b)
    print(f"full-progress changed pixels  phrase={phrase_n}  whole={whole_n}")
    assert 0 < phrase_n < whole_n, (
        f"phrase ({phrase_n}) should be a strict subset of whole ({whole_n})")

    # 4: an unmatched phrase falls back to whole-element sweep (no crash).
    miss = build(highlight=True, highlight_text="no such words here")
    miss_n = changed_pixels(miss.render_frame(t), b)
    print(f"unmatched-phrase fallback changed pixels = {miss_n}")
    assert miss_n > phrase_n, "fallback should cover more than the phrase"

    print("\nOK - highlight sweep renders, grows, and respects phrase selection.")


def test_document_highlight():
    """DocumentHighlightRenderer's highlight_text drives the marker sweep."""
    common = dict(text=TEXT, width=960, height=540, text_size=26,
                  document_width=720)
    base = DocumentHighlightRenderer(highlight_text=None, **common)
    hl = DocumentHighlightRenderer(highlight_text=PHRASE, **common)
    t = 2.0  # highlight starts 1.1, lasts 0.9 -> full
    b = base.render_frame(t)
    diff = changed_pixels(hl.render_frame(t), b)
    print(f"document_highlight changed pixels (phrase) = {diff}")
    assert diff > 0, "highlight_text did not drive the sweep in DocumentHighlight"


def test_preset():
    """EffectPresets.highlight_sweep returns a configured Underline."""
    fx = EffectPresets.highlight_sweep(start=1.0, duration=0.9,
                                       highlight_text=PHRASE)
    assert len(fx) == 1 and isinstance(fx[0], Underline)
    assert fx[0].style == "highlight" and fx[0].highlight_text == PHRASE
    print("EffectPresets.highlight_sweep OK")


if __name__ == "__main__":
    main()
    test_document_highlight()
    test_preset()
    print("\nALL OK")
