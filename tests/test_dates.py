"""date_text -> (year_from, year_to) — honesty tests.

Designed against the REAL strings in the corpus (14,069 distinct over 96,752 rows), not imagined
ones. Two of these are regressions for bugs the characterisation pass caught, and they are the
reason the module is worth its length.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from nolan.imagelib.dates import parse_years                            # noqa: E402


@pytest.mark.parametrize("text,want", [
    # the shapes, by corpus frequency
    ("1857", (1857, 1857)),                     # 26,284 rows
    ("c. 1560", (1560, 1560)),                  # 14,873 — precision is not modelled, deliberately
    ("1830/33", (1830, 1833)),                  # 4,426 — truncated range
    ("1830-33", (1830, 1833)),                  # 3,446
    ("1830-1833", (1830, 1833)),                # 2,926
    ("19th century", (1800, 1899)),             # 2,364
    ("before 1500", (1475, 1500)),              # 460
    ("1850s", (1850, 1859)),                    # a DECADE
    ("1800s", (1800, 1899)),                    # a CENTURY — see the module docstring
    ("early 1900s", (1900, 1939)),
    ("late 17th century", (1660, 1699)),
    ("mid 17th century", (1630, 1669)),
    ("Chola period, about 12th century", (1100, 1199)),   # date buried in prose
])
def test_the_common_shapes(text, want):
    assert parse_years(text) == want


@pytest.mark.parametrize("text", ["n.d.", "N.D.", "Date unknown", "Unknown", "not dated",
                                  "undated", "", None])
def test_no_date_is_a_real_answer(text):
    """4,652 rows say "n.d.". Inventing a range for them would drop every one into every date
    filter that touched their era."""
    assert parse_years(text) is None


def test_bce_ranges_are_not_treated_as_truncated():
    """REGRESSION. A BCE range is written HIGH to LOW and both numbers are complete years, but
    the truncated-range expander assumed ascending, failed, and collapsed the whole thing:
    "330-320 BCE" came back as (-330, -330), and "5800-4000 BCE" as (-5800, -5800)."""
    assert parse_years("330-320 BCE") == (-330, -320)
    assert parse_years("about 924-889 BCE") == (-924, -889)
    assert parse_years("5800-4000 BCE") == (-5800, -4000)
    assert parse_years("c. 4700-2920 BCE") == (-4700, -2920)


def test_a_range_that_straddles_zero():
    """REGRESSION. The era marker sits BETWEEN the numbers in "100 BCE-500 CE", so the plain
    range pattern never saw a digit either side of the dash; the string fell through to the
    single-year path and returned (-500, -100) — right magnitudes, both on the wrong side."""
    assert parse_years("100 BCE-500 CE") == (-100, 500)
    assert parse_years("20 BCE-10 CE") == (-20, 10)


def test_a_century_range_keeps_both_centuries():
    """REGRESSION. "5th-6th century" writes the word once for two ordinals, and a combined
    pattern saw only the second — silently losing a hundred years as (500, 599)."""
    assert parse_years("5th-6th century") == (400, 599)
    assert parse_years("12th/13th centuries") == (1100, 1299)


def test_short_years_need_an_era_marker():
    """Without one, 1-2 digit numbers are dynasty numbers, plate numbers and catalogue
    references — not years. Refusing is right; guessing would poison every date filter."""
    assert parse_years("9-23 CE") == (9, 23)
    assert parse_years("c. 50 BCE") == (-50, -50)
    assert parse_years("54-68") is None
    assert parse_years("Dynasty 22") is None


def test_ranges_always_run_low_to_high():
    """A filter does `year_from <= x <= year_to`; an inverted range matches nothing, silently."""
    for text in ("1830-1833", "330-320 BCE", "5th-6th century", "100 BCE-500 CE",
                 "1800s", "before 1500", "c. 4700-2920 BCE"):
        lo, hi = parse_years(text)
        assert lo <= hi, f"{text!r} produced an inverted range ({lo}, {hi})"


def test_all_four_dash_characters():
    """Museums use hyphen, en dash, em dash and minus — often in the same field."""
    for dash in ("-", "–", "—", "−"):
        assert parse_years(f"1830{dash}1833") == (1830, 1833)
