"""Speak-ready text normalization for TTS (A1 of the voice program).

OmniVoice is fed section prose verbatim after markdown stripping, so raw digits
and symbols ("$4.2B", "90%", "1888", "3.14", "1st") get mangled. This module is
a pure-Python, deterministic normalizer that expands them to spoken words BEFORE
synthesis. No external deps (num2words/inflect are not installed) — the number
speller is table-tested in tests/test_tts_normalize.py.

Design notes / heuristics:
  - Currency amounts and percentages are read as CARDINALS ("$2000" → "two
    thousand dollars"), never as years.
  - A BARE 4-digit integer in 1100–2099 is read as a YEAR ("1888" → "eighteen
    eighty eight", "2019" → "twenty nineteen"); a COMMA-grouped number ("1,500")
    is always a cardinal — commas signal a quantity, not a year. This favors the
    year-heavy prose of video essays while keeping "1,500 people" correct.
  - `acronyms` lets a caller spell out specific tokens (e.g. {"CEO": "C E O"});
    nothing is auto-spelled, since "NASA"→"nasa" but "CEO"→"C E O" is not
    machine-decidable safely.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_SCALES = [(10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"),
           (10 ** 3, "thousand")]
_MAGNITUDE = {"k": "thousand", "m": "million", "b": "billion", "bn": "billion",
              "thousand": "thousand", "million": "million", "billion": "billion",
              "trillion": "trillion"}
# cardinal-word -> ordinal-word for the irregular tail forms
_ORD_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                  "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _under_1000(n: int) -> list:
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10])
        if n % 10:
            words.append(_ONES[n % 10])
    elif n > 0:
        words.append(_ONES[n])
    return words


def cardinal(n: int) -> str:
    """Non-negative/negative integer → spoken cardinal ('1234' → 'one thousand …')."""
    if n < 0:
        return "minus " + cardinal(-n)
    if n == 0:
        return "zero"
    parts = []
    for scale, name in _SCALES:
        if n >= scale:
            parts += _under_1000(n // scale) + [name]
            n %= scale
    if n:
        parts += _under_1000(n)
    return " ".join(parts)


def ordinal(n: int) -> str:
    """Integer → spoken ordinal ('21' → 'twenty first')."""
    words = cardinal(n).split()
    last = words[-1]
    if last in _ORD_IRREGULAR:
        words[-1] = _ORD_IRREGULAR[last]
    elif last.endswith("y"):
        words[-1] = last[:-1] + "ieth"
    else:
        words[-1] = last + "th"
    return " ".join(words)


def year(n: int) -> str:
    """Integer 1100–2099 → spoken year ('1905' → 'nineteen oh five')."""
    if 2000 <= n <= 2009:
        return cardinal(n)                    # two thousand (nine)
    hi, lo = divmod(n, 100)
    if lo == 0:
        return cardinal(hi) + " hundred"       # nineteen hundred
    if lo < 10:
        return cardinal(hi) + " oh " + _ONES[lo]   # nineteen oh five
    return cardinal(hi) + " " + cardinal(lo)   # nineteen ninety six


def _digits(s: str) -> str:
    return " ".join(_ONES[int(c)] for c in s)


def _decimal(intpart: str, frac: str) -> str:
    whole = cardinal(int(intpart.replace(",", ""))) if intpart else "zero"
    return f"{whole} point {_digits(frac)}"


def _say_scalar(s: str, *, allow_year: bool = False) -> str:
    """A single numeric token (may carry commas / a decimal) → spoken words."""
    s = s.strip()
    had_comma = "," in s
    if "." in s:
        intpart, frac = s.split(".", 1)
        return _decimal(intpart, frac)
    n = int(s.replace(",", ""))
    if allow_year and not had_comma and 1100 <= n <= 2099:
        return year(n)
    return cardinal(n)


# A number token: optional thousands-grouped commas (,\d{3}) + optional decimal.
# Commas must be proper separators so a trailing comma ("1888,") is NOT captured
# (which would misflag a bare year as a comma-quantity → cardinal instead of year).
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"


def normalize_for_speech(text: str, *, acronyms: Optional[Dict[str, str]] = None) -> str:
    """Expand numbers, currency, percentages, ranges, ordinals & decimals to words.

    Order matters: currency/percent/ranges consume their numbers before the bare
    integer/decimal passes, so "$4.2B" and "90%" are never double-processed.
    """
    if not text:
        return text or ""
    t = text

    # 1) currency: $4.2B, $1,234, $5 million, $2000
    #    word magnitudes need a leading space; single-letter magnitudes must be
    #    ATTACHED (so "$5 basis" is not read as billions, and no trailing space is eaten).
    def _cur(m):
        num = _say_scalar(m.group(1))                     # cardinal (never year)
        mag = (m.group(2) or "").strip().lower()
        mag_w = (" " + _MAGNITUDE[mag]) if mag in _MAGNITUDE else ""
        return f"{num}{mag_w} dollars"
    t = re.sub(rf"\$\s?({_NUM})(\s(?:trillion|billion|million|thousand|bn)\b|[bmkBMK]\b)?",
               _cur, t)

    # 2) percent: 90%, 3.5%
    t = re.sub(rf"({_NUM})\s?%", lambda m: f"{_say_scalar(m.group(1))} percent", t)

    # 3) numeric ranges: 2019–2021, 10-20  (each side keeps year logic)
    t = re.sub(rf"({_NUM})\s?[–—-]\s?({_NUM})",
               lambda m: f"{_say_scalar(m.group(1), allow_year=True)} to "
                         f"{_say_scalar(m.group(2), allow_year=True)}", t)

    # 4) ordinals: 1st, 2nd, 21st
    t = re.sub(r"(\d+)(?:st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t)

    # 5) bare decimals: 3.14
    t = re.sub(r"(\d+)\.(\d+)", lambda m: _decimal(m.group(1), m.group(2)), t)

    # 6) bare integers (incl. comma-grouped): 1888 (year) / 1,500 (cardinal)
    t = re.sub(r"\d+(?:,\d{3})*", lambda m: _say_scalar(m.group(0), allow_year=True), t)

    # 7) caller-specified acronyms (whole-word, case-sensitive)
    if acronyms:
        for k, v in acronyms.items():
            t = re.sub(rf"\b{re.escape(k)}\b", v, t)
    return t
