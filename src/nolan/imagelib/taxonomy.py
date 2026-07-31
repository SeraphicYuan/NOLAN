"""What KIND of picture this is — derived from the catalog, never asked of a model.

A 50-row validation pass asked a VLM for `image_kind` and then compared it against regex
bucketing of the institution's own `classification` field. The regex won on every row where they
disagreed, which is unsurprising once stated plainly: the museum already catalogued the object,
and a vision model squinting at a thumbnail is guessing at a fact somebody else recorded.

So this module is the third knowledge source in the caption design — catalog-derived, free, and
off-limits to the VLM:

    catalog record  -> title, creator, date, medium, place, classification, department  (here)
    collection      -> rights, era, topics
    artist          -> movement, period, style
    VLM caption     -> what is actually DEPICTED, and nothing else

`image_kind` is a COARSE SUBJECT CATEGORY for retrieval filtering ("show me textiles"). It is
deliberately NOT the framing decision — whether a picture is an object on a sweep, how much dead
margin it carries, whether it is round — because `nolan.pixels` measures all of that from the
actual image and a category name cannot. Two different questions; keeping them apart is what
stopped `banner_suspect` refusing 4 of 4 museum object photographs.

CLOSED VOCABULARY with a LOUD fallback (checklist class 3: exact-string matching on an open
vocabulary is how `visual_type` made three consumers silently see zero eligible rows). Anything
unmapped becomes `unknown` and is COUNTED, so a source whose vocabulary we do not understand
shows up as a number instead of quietly becoming "object".
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional, Tuple

# The canonical set. Coarse on purpose: every bucket has to be one a human would actually filter
# on, and one the source's own words support without interpretation.
IMAGE_KINDS: Tuple[str, ...] = (
    "painting", "print", "drawing", "photograph", "sculpture", "textile",
    "ceramic", "metalwork", "coin", "glass", "furniture", "book", "map",
    "object", "unknown",
)

# ORDER MATTERS — first match wins, so the specific sits above the general. Sourced from the real
# vocabularies, not invented: the Met publishes 961 distinct `Classification` values (pipe-joined
# compounds like "Photographs|Ephemera", hyphenated sub-types like "Textiles-Woven"), and the Art
# Institute publishes 119 lowercase values that MIX classification with medium ("painting" and
# "oil on canvas" both appear in the same column).
_RULES: Tuple[Tuple[str, str], ...] = (
    # Coins first: "Medals and Plaquettes" is metalwork by material and a coin by shape, and the
    # shape is what matters downstream — coin photography is the dead-margin extreme (29-32% of
    # the frame is grey sweep).
    ("coin", r"\bcoins?\b|numismat|\bmedal|plaquette|\bcurrency\b"),
    # Photographs before books/ephemera: "Photographs|Ephemera" is a photograph.
    ("photograph", r"\bphotograph|daguerreotype|ambrotype|tintype|albumen|"
                   r"gelatin silver|calotype|negative|cyanotype|autochrome"),
    ("print", r"\bprints?\b|etching|engraving|lithograph|woodcut|woodblock|drypoint|"
              r"mezzotint|aquatint|intaglio|screenprint|serigraph|linocut|"
              r"\bimpression\b|monotype"),
    ("drawing", r"\bdrawings?\b|\bpastel|\bchalk\b|\bgraphite\b|charcoal|watercolor|"
                r"watercolour|\bgouache\b|pen and ink|\bsketch|calligraph|\brubbing\b|"
                r"\bink\b|\bcartoon\b"),
    ("painting", r"\bpainting|\boil on\b|\btempera\b|\bfresco\b|\bicon\b|miniature"),
    # Garments are textiles. The Met catalogues them by the thing rather than the material
    # ("Dress", "Collar", "Cap", "Shoes", "Handkerchief", "Button"), which is why the first pass
    # filed 1,400 of them under `unknown`.
    ("textile", r"\btextile|\bweaving|tapestr|\blace\b|\bvelvet|embroider|\bcostume|"
                r"\bgarment|\brug\b|\bcarpet|\bquilt|\bsampler\b|\bfan\b|\bsilk\b|"
                r"\bdress\b|\bcollar\b|\bcap\b|\bshoes?\b|\bhandkerchief|\bbutton\b|"
                r"\bhat\b|\bglove|\bshawl\b|\bapron\b|\bbodice\b|\bsleeve\b|"
                r"\btrimming|\bribbon\b|\bfragment.*textile|\bcoat\b|\bstocking"),
    ("ceramic", r"\bceramic|porcelain|\bpottery|\bvases?\b|\bterracotta|earthenware|"
                r"stoneware|\bmajolica|\bfaience"),
    ("glass", r"\bglass\b|stained glass|\bcameo glass\b"),
    ("furniture", r"\bfurniture|\bwoodwork|\bcabinet\b|\bchair\b|\btable\b|\bscreen\b|"
                  r"\bcasket\b|\bchest\b"),
    ("book", r"\bbooks?\b|\bcodices\b|\bcodex\b|manuscript|\bephemera\b|\bfolio\b|"
             r"\balbum\b|bookbinding|\bbroadside"),
    ("map", r"\bmaps?\b|\bcartograph|\batlas\b|\bglobe\b"),
    ("sculpture", r"\bsculptur|statuett?e|\bbust\b|\bbronzes?\b|\brelief\b|\bfigurine|"
                  r"\bcarving|\bstatue\b|\bmask\b"),
    ("metalwork", r"\bmetalwork|\bsilver\b|\bgold\b|\bjewelry|\bjewellery|\bbrass\b|"
                  r"\bpewter\b|\biron\b|\bornament|\barms\b|\barmor|\barmour|"
                  r"\benamel|\bwatch\b|\bclock\b|\bhelmet|\barrowhead|\barchery|"
                  r"\bsword\b|\bdagger\b|\bshield\b|\bfirearm|\bgun\b|\bknife\b|"
                  r"\bspur\b|\bbuckle\b"),
    # The catch-all for physical things the source named but we do not bucket: vessels, jade,
    # stucco, tools. Distinct from `unknown`, which means the source said NOTHING usable.
    ("object", r"\bvessel|\bjade\b|\bstucco\b|\bbowl\b|\bplate\b|\bjar\b|\bewer\b|"
               r"\bpitcher\b|\bcup\b|\bdish\b|\bcontainer|\bimplement|\btool\b|"
               r"\binstrument|\bseal\b|\bamulet\b|\bcylinder\b|\bstone\b|\bwood\b|"
               r"\bivor|\bceremonial|\btablet|\bsnuff\b|\bgems?\b|\bbone\b|\bpapyrus\b|"
               r"\blacquer|\bamber\b|\bbasketry\b|\bframe|\bstencil|\bsealing|"
               r"\bmarble\b|\bsandstone\b|\bterracotta|\bscroll\b|\bfragment"),
)

_COMPILED = tuple((kind, re.compile(pat, re.I)) for kind, pat in _RULES)


def image_kind(*candidates: Optional[str]) -> str:
    """Bucket a row into one of :data:`IMAGE_KINDS`, from the source's own words.

    Pass the fields in order of authority — classification first, then medium, then a type or
    tag. The Art Institute is the reason more than one is accepted: its single column holds
    "painting" for one row and "oil on canvas" for the next, so a single-field lookup would
    return `unknown` for a third of a collection that is perfectly well described.
    """
    for value in candidates:
        text = (value or "").strip()
        if not text:
            continue
        for kind, rx in _COMPILED:
            if rx.search(text):
                return kind
    return "unknown"


def kind_coverage(rows: Iterable[Tuple[Optional[str], ...]]) -> Dict[str, int]:
    """Count kinds over an iterable of field-tuples — the honesty instrument.

    A derivation whose fallthrough rate nobody measures is a silent cap: it reports a tidy set of
    buckets while quietly filing an unknown share under `unknown`. Run this whenever the rules or
    a source's vocabulary changes, and look at what fell through.
    """
    out: Dict[str, int] = {k: 0 for k in IMAGE_KINDS}
    for fields in rows:
        out[image_kind(*fields)] += 1
    return out
