"""P0.2 — legibility as a wired invariant.

The "footage text inherits dark paper ink" bug bit twice (`.stmt.footage-t` in v1, `.footage
.slnum/.kick/.sllabel` in v2). This honesty test parses the CSS `compose.py` emits and FAILS if any
selector scoped to an over-media register (`.footage …`, `.stmt.footage-t`, `.cmp-*.footage`) sets
`color` to a dark token — so the regression can't ship again.
"""
import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "render-service" / "_lab_hyperframes" / "bridge" / "compose.py"

# tokens that are DARK ink (illegible over footage). var(--text)/--ink are the paper-body ink.
_DARK_VARS = {"var(--text)", "var(--ink)"}


def _compose_css() -> str:
    txt = COMPOSE.read_text(encoding="utf-8")
    m = re.search(r'CSS\s*=\s*"""(.*?)"""', txt, re.S)
    assert m, "compose.py CSS block not found"
    return m.group(1)


def _luma(hexstr: str):
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255            # relative luminance 0..1


def _is_dark(color: str) -> bool:
    c = color.strip().lower()
    if c in _DARK_VARS:
        return True
    m = re.match(r"#([0-9a-f]{3,6})", c)
    if m:
        lum = _luma("#" + m.group(1))
        return lum is not None and lum < 0.5
    return False


def _rules(css: str):
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


def test_over_media_text_is_light():
    offenders = []
    for sel, body in _rules(_compose_css()):
        s = sel.lower()
        if "footage" not in s:                                    # only over-media registers
            continue
        if "hlwrap" in s or "hlblock" in s:                       # text ON the accent bar is meant to be dark
            continue
        cm = re.search(r"(?:^|;)\s*color\s*:\s*([^;]+)", body)
        if cm and _is_dark(cm.group(1)):
            offenders.append((sel, cm.group(1).strip()))
    assert not offenders, ("over-media (.footage…) text set to DARK ink — illegible over an image/clip. "
                           f"The paper→footage-ink regression is back: {offenders}")


def test_the_guard_catches_a_reintroduced_dark_token():
    # sanity: the checker itself must flag a dark footage rule
    bad = ".footage .kick{color:var(--text);}"
    hit = [sel for sel, body in _rules(bad)
           if "footage" in sel.lower() and _is_dark(re.search(r"color:\s*([^;]+)", body).group(1))]
    assert hit == [".footage .kick"]
