"""Turn a museum's date STRING into a numeric year range you can filter on.

`date_text` is 99% populated across the corpus and completely unfilterable as it stands: 14,069
distinct strings for 96,752 rows. "18th-century Japanese prints" is a query the catalog obviously
knows the answer to and cannot answer, purely because the answer is prose.

DESIGNED AGAINST THE REAL STRINGS, not imagined ones. The shapes, by frequency:

    26,284  ####                    1857
    14,873  c. ####                 c. 1560
     4,646  n.d.                    -> no answer, and that is a real answer
     4,526  ####s                   1800s          <- see THE AMBIGUITY below
     4,426  ####/##                 1830/33        <- truncated range
     3,446  ####–##                 1830–33
     2,926  ####–####               1830–1833
     2,364  ##th century            19th century
       787  ### BCE–### CE          100 BCE–500 CE
       590  ###–### BCE             330–320 BCE
       460  before ####

Plus 11% with no 3-4 digit run at all ("Late 17th century", "Mid–late 19th century", "Chola
period, about 12th century") and long prose with the date buried in it ("Third Intermediate
Period, Dynasty 22, reign of Osorkon I (about 924–889 BCE)").

THE AMBIGUITY, decided explicitly rather than silently: `1800s` could be the decade 1800-1809 or
the century 1800-1899. Both readings are in use. This corpus writes "19th century" 996 times AND
"1800s" 1,256 times, so they cannot be synonyms in the cataloguer's head — but "1850s" (a decade)
and "1800s" (a century) are both spelled the same way. The rule adopted: **a `####s` ending in
"00" is a CENTURY, anything else is a DECADE.** So 1800s -> 1800-1899, 1850s -> 1850-1859. It is
a guess at intent, it is wrong for someone who meant the 1800-1809 decade, and it is written down
here so the next reader can change it knowing what they are changing.

BCE is negative and ORDERED: "924–889 BCE" -> (-924, -889), because -924 < -889 and a range must
run low to high whatever the era.

Precision is not modelled. "c. 1560" and "1560" both yield (1560, 1560); a filter for
"1550-1570" should match both, and pretending we know the error bars would be false rigour.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# en dash, em dash, minus, hyphen — museums use all four, often in one field.
_DASH = re.compile(r"[‐-―−\-]")
_BCE = re.compile(r"\bB\.?\s?C\.?(?:E\.?)?\b", re.I)
_CE = re.compile(r"\b(?:A\.?\s?D\.?|C\.?\s?E\.?)\b", re.I)

# Ordinals are found SEPARATELY from the word "century", because "5th-6th century" writes the
# word once for two ordinals and a combined pattern silently sees only the second — which read
# "5th-6th century" as 500-599 and lost a hundred years without complaining.
_ORDINAL = re.compile(r"(\d{1,2})\s*(?:st|nd|rd|th)\b", re.I)
_HAS_CENTURY = re.compile(r"centur(?:y|ies)", re.I)
_DECADE = re.compile(r"\b(\d{3,4})s\b")
_RANGE = re.compile(r"\b(\d{3,4})\s*/\s*(\d{1,4})\b|\b(\d{3,4})\s*-\s*(\d{1,4})\b")
# "100 BCE-500 CE" — the era marker sits BETWEEN the numbers, so the plain range pattern never
# sees a digit either side of the dash and the string falls through to the single-year path,
# where it came back as (-500, -100): the right magnitudes, both on the wrong side of zero.
_MIXED_ERA = re.compile(
    r"(\d{1,4})\s*B\.?\s?C\.?E?\.?\s*-\s*(\d{1,4})\s*(?:C\.?\s?E\.?|A\.?\s?D\.?)", re.I)
_YEAR = re.compile(r"\b(\d{3,4})\b")
_SHORT_YEAR = re.compile(r"\b(\d{1,4})\b")
_UNKNOWN = re.compile(r"^\s*(?:n\.?\s?d\.?|date\s+unknown|unknown|not\s+dated|undated)\s*$", re.I)
_BEFORE = re.compile(r"\b(?:before|prior to|by)\b", re.I)
_AFTER = re.compile(r"\b(?:after|from)\b", re.I)


def _complete(start: int, end: int) -> int:
    """Expand a truncated range end: 1830/33 -> 1833, 1830-3 -> 1833."""
    if end >= start:
        return end
    for mag in (10, 100, 1000):
        if end < mag:
            cand = (start // mag) * mag + end
            if cand >= start:
                return cand
    return start


def parse_years(text: Optional[str]) -> Optional[Tuple[int, int]]:
    """`date_text` -> (year_from, year_to) inclusive, or None when there is no answer.

    None is a first-class result — "n.d." means the museum does not know, and inventing a range
    for it would put 4,646 rows into every date filter that touched their era.
    """
    if not text:
        return None
    s = _DASH.sub("-", str(text)).strip()
    if not s or _UNKNOWN.match(s):
        return None

    # Era. A string can carry BOTH ("100 BCE-500 CE"), so track which side each belongs to.
    has_bce = bool(_BCE.search(s))
    mixed = has_bce and bool(_CE.search(s))

    # --- straddles zero: "100 BCE-500 CE" ----------------------------------------------------
    mm = _MIXED_ERA.search(s)
    if mm:
        return (-int(mm.group(1)), int(mm.group(2)))

    # --- centuries: "19th century", "5th-6th century", "late 17th century" -------------------
    cents = _ORDINAL.findall(s) if _HAS_CENTURY.search(s) else []
    if cents:
        nums = [int(c) for c in cents]
        lo_c, hi_c = min(nums), max(nums)
        if has_bce:
            # 5th century BCE spans -500..-401
            return (-(lo_c * 100), -((hi_c - 1) * 100 + 1)) if lo_c == hi_c else \
                   (-(hi_c * 100), -((lo_c - 1) * 100 + 1))
        lo = (lo_c - 1) * 100
        hi = hi_c * 100 - 1
        low = s.lower()
        if lo_c == hi_c:                       # modifiers only make sense on a single century
            if "early" in low:
                hi = lo + 39
            elif "late" in low:
                lo = hi - 39
            elif "mid" in low:
                lo, hi = lo + 30, lo + 69
        return (lo, hi)

    # --- decades / centuries written as "1800s" ---------------------------------------------
    dm = _DECADE.search(s)
    if dm:
        base = int(dm.group(1))
        span = 99 if base % 100 == 0 else 9      # THE AMBIGUITY — see the module docstring
        lo, hi = base, base + span
        low = s.lower()
        if span == 99:
            if "early" in low:
                hi = lo + 39
            elif "late" in low:
                lo = hi - 39
            elif "mid" in low:
                lo, hi = lo + 30, lo + 69
        return (-hi, -lo) if has_bce else (lo, hi)

    # --- explicit ranges: 1830/33, 1830-1833, 330-320 BCE ------------------------------------
    rm = _RANGE.search(s)
    if rm:
        a, b = (rm.group(1), rm.group(2)) if rm.group(1) else (rm.group(3), rm.group(4))
        start, end = int(a), int(b)
        if has_bce:
            # A BCE range is written HIGH to LOW and both numbers are complete years, so
            # `_complete` must not touch it: it read "330-320 BCE" as a truncated ascending
            # range, failed to expand it, and collapsed the whole thing to (-330, -330).
            return (-max(start, end), -min(start, end))
        end = _complete(start, end)
        return (min(start, end), max(start, end))

    # --- a single year, possibly buried in prose ---------------------------------------------
    years = [int(y) for y in _YEAR.findall(s)]
    if not years and (has_bce or _CE.search(s)):
        # Only with an explicit era do 1-2 digit numbers mean YEARS ("9-23 CE"); without one
        # they are dynasty numbers, plate numbers and catalogue references.
        years = [int(y) for y in _SHORT_YEAR.findall(s)]
    if not years:
        return None
    lo, hi = min(years), max(years)
    if has_bce:
        lo, hi = -hi, -lo
    if _BEFORE.search(s) and lo == hi:
        return (lo - 25, hi)                      # "before 1500" -> a quarter-century window
    if _AFTER.search(s) and lo == hi:
        return (lo, hi + 25)
    return (lo, hi)
