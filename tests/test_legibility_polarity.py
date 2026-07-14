"""Legibility polarity (P2a) — authored emphasis must stay readable on a DARK ground/theme. Three
homer-run defects, each a CSS contract: the footage operative, the highlighted diagram root, and the
newshead card. These assert the composer CSS carries the fix (a render is the visual proof; this is the
grep-verifiable contract per the wiring checklist)."""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

CSS = compose.CSS


def test_footage_operative_has_persistent_accent_backing():
    """On a dark footage ground the operative gets a PERSISTENT accent bg (not just the swept bar),
    so a late-spoken operative isn't dark-on-dark before its sweep fires (homer F5/s3)."""
    block = CSS.split(".stmt.footage-t .hlwrap{", 1)[1][:200]
    assert "background:var(--accent)" in block and "var(--accent-ink)" in block


def test_dark_diagram_highlighted_root_label_is_light():
    """A highlighted root node keeps a dark bg (accent border as the highlight) + LIGHT ink, instead of
    the dark-on-dark the .root/.hl combination produced (homer F6 'HOMER')."""
    assert ".dg-dark .dgnode.root.hl .lab{color:#F6F7F6" in CSS


def test_dark_newshead_variant_is_legible():
    """The dark-newsprint variant exists (no bright hole) and its highlighted phrase has dark ink on a
    persistent accent bg (homer ⑥)."""
    assert ".nh-dark .nhcard{" in CSS
    assert ".nh-dark .nhhl-wrap .w{color:var(--accent-ink)" in CSS
    assert ".nh-dark .nhhead{color:#EDEBE4" in CSS
