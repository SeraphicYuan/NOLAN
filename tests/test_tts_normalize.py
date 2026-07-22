"""A1: speak-ready text normalization — table-driven."""

import pytest

from nolan.tts_normalize import normalize_for_speech, cardinal, ordinal, year


@pytest.mark.parametrize("n,expected", [
    (0, "zero"), (7, "seven"), (13, "thirteen"), (20, "twenty"), (42, "forty two"),
    (100, "one hundred"), (215, "two hundred fifteen"), (1000, "one thousand"),
    (1234, "one thousand two hundred thirty four"),
    (1000000, "one million"), (2500000, "two million five hundred thousand"),
    (-5, "minus five"),
])
def test_cardinal(n, expected):
    assert cardinal(n) == expected


@pytest.mark.parametrize("n,expected", [
    (1, "first"), (2, "second"), (3, "third"), (5, "fifth"), (8, "eighth"),
    (9, "ninth"), (12, "twelfth"), (20, "twentieth"), (21, "twenty first"),
    (100, "one hundredth"), (4, "fourth"),
])
def test_ordinal(n, expected):
    assert ordinal(n) == expected


@pytest.mark.parametrize("n,expected", [
    (2019, "twenty nineteen"), (1996, "nineteen ninety six"), (2000, "two thousand"),
    (2005, "two thousand five"), (2010, "twenty ten"), (1900, "nineteen hundred"),
    (1905, "nineteen oh five"), (1888, "eighteen eighty eight"),
])
def test_year(n, expected):
    assert year(n) == expected


@pytest.mark.parametrize("raw,expected", [
    # currency (cardinal, never year) + magnitudes
    ("$4.2B raised", "four point two billion dollars raised"),
    ("$5 million deal", "five million dollars deal"),
    ("costs $1,234 today", "costs one thousand two hundred thirty four dollars today"),
    ("$2000 fine", "two thousand dollars fine"),
    # percent
    ("up 90%", "up ninety percent"),
    ("a 3.5% cut", "a three point five percent cut"),
    # years (bare 4-digit 1100-2099) vs comma-quantities
    ("founded in 1888", "founded in eighteen eighty eight"),
    ("by 2019 revenue", "by twenty nineteen revenue"),
    ("hired 1,500 people", "hired one thousand five hundred people"),
    # ranges
    ("from 2019-2021", "from twenty nineteen to twenty twenty one"),
    ("10-20 units", "ten to twenty units"),
    # ordinals + decimals
    ("the 1st time", "the first time"),
    ("pi is 3.14", "pi is three point one four"),
    # mixed / no-op
    ("no numbers here", "no numbers here"),
    ("", ""),
])
def test_normalize(raw, expected):
    assert normalize_for_speech(raw) == expected


def test_acronyms_opt_in():
    assert normalize_for_speech("the CEO said", acronyms={"CEO": "C E O"}) == "the C E O said"
    # not auto-spelled without the map
    assert normalize_for_speech("the CEO said") == "the CEO said"
