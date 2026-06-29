"""Detect the dominant on-screen language for a presentation from its script.

Heuristic, dependency-free: classify each "letter" character by Unicode block and
pick the dominant script. Good enough to drive the skill's on-screen-language
enforcement (so chapters don't inherit the bundled example's language).

Usage:
    python detect_lang.py <script.md>   # prints e.g. "en  English"
"""
from __future__ import annotations

import sys
import unicodedata
from collections import Counter
from pathlib import Path


def _bucket(ch: str) -> str | None:
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
        return "han"          # CJK ideographs (zh, also ja kanji)
    if 0x3040 <= o <= 0x30FF:
        return "kana"         # hiragana/katakana -> ja
    if 0xAC00 <= o <= 0xD7A3:
        return "hangul"       # ko
    if 0x0400 <= o <= 0x04FF:
        return "cyrillic"     # ru, ...
    if ch.isalpha() and o < 0x250:
        return "latin"        # en and most european
    return None


_LANG = {"latin": ("en", "English"), "han": ("zh", "Chinese"),
         "kana": ("ja", "Japanese"), "hangul": ("ko", "Korean"),
         "cyrillic": ("ru", "Cyrillic")}


def detect(text: str) -> tuple[str, str, dict]:
    # Count CJK/Hangul/Cyrillic per character (≈ one word each), but Latin per
    # *word run* — so "10 hanzi" isn't out-voted by the letters of 3 English words.
    counts: Counter[str] = Counter()
    in_latin = False
    for ch in text:
        b = _bucket(ch)
        if b == "latin":
            if not in_latin:
                counts["latin"] += 1   # one count per contiguous Latin run (a word)
                in_latin = True
        else:
            in_latin = False
            if b:
                counts[b] += 1
    if not counts:
        return "en", "English", {}
    # kana presence implies Japanese even if han dominates (kanji+kana mix)
    if counts.get("kana", 0) > 0 and counts.get("han", 0) > 0:
        top = "kana"
    else:
        top = counts.most_common(1)[0][0]
    code, name = _LANG.get(top, ("en", "English"))
    return code, name, dict(counts)


if __name__ == "__main__":
    src = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    code, name, counts = detect(src)
    print(f"{code}\t{name}\t{counts}")
