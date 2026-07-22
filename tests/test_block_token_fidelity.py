"""Block token-fidelity (P0 of the composition-quality program).

Every block must render in the ACTIVE theme's tokens. The recurring failure is the full-bleed PAGE
ground: --shell is the canvas on a normal theme, but on an INVERTED-CARD theme (dark --shell tuned so
--text is legible on a light --surface, e.g. bauhaus-bold #1a1a1a shell / #f4f1ea surface) a raw --shell
ground renders a DARK panel under light content — the chart + code 'lone odd-one-out' bug the composer
already fixed for `statement` via _page_bg()/media_ground but had not swept across all blocks.

Two deterministic gates (no headless render needed):
  1. source-scan — no block emits a raw `inset:0;background:var(--shell)` full-bleed ground; they must
     call _page_bg() (which is shell-textsafe). This is the regression guard.
  2. computed — for EVERY theme, the token _page_bg() resolves to keeps --text legible (>= 3:1). This
     validates the whole chain (_theme_shell_textsafe + the fallback) across the real theme library.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
for _p in (str(REPO / "src"), str(BRIDGE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import compose  # noqa: E402

COMPOSE_SRC = (BRIDGE / "compose.py").read_text(encoding="utf-8")
THEMES = sorted(d.name for d in (REPO / "themes").iterdir() if (d / "tokens.css").exists())


def _lum(hexstr):
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    ch = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _tok(css, name):
    m = re.search(rf"--{name}\s*:\s*(#[0-9a-fA-F]{{3,6}})", css)
    return m.group(1) if m else None


def test_no_block_paints_a_raw_shell_fullbleed_ground():
    """A full-bleed page ground that TEXT sits on must route through _page_bg(); a raw var(--shell) goes
    dark on an inverted-card theme. This is the guard that would have caught the chart + code bug.

    EXEMPT: `.dgbg` (the diagram ground). It is a CARD-CONTAINER — the nodes sit on var(--surface) cards,
    not on the ground — so var(--shell) is correct AND intentional: on inverted themes it gives the
    dark-canvas + light-cards look, where _page_bg() (surface) would collapse ground==nodes. No direct text
    on it, so the dark-on-light risk doesn't apply."""
    src = re.sub(r"\.dgbg\{[^}]*\}", "", COMPOSE_SRC)   # drop the exempt card-container ground
    hits = re.findall(r"inset:\s*0;\s*background:\s*var\(--shell\)", src)
    assert not hits, (
        f"{len(hits)} full-bleed ground(s) hardcode var(--shell) — route through _page_bg() so "
        f"inverted-card themes (dark shell / light surface) don't render a dark panel under light content"
    )


def test_page_bg_helper_is_the_only_page_ground_decider():
    """media_ground must resolve its canvas through _page_bg() (single source of truth), not re-derive
    the shell/surface choice inline — so the decision lives in exactly one place."""
    assert "canvas = _page_bg()" in COMPOSE_SRC, "media_ground should call _page_bg() for its canvas"


def test_page_bg_keeps_text_legible_for_every_theme():
    """For every theme, the resolved full-bleed page background keeps --text legible (>= 3:1). If a
    theme's --shell is the wrong polarity, _page_bg() must fall back to --surface — this checks it does."""
    bad = []
    for t in THEMES:
        css = (REPO / "themes" / t / "tokens.css").read_text(encoding="utf-8")
        shell, surface, text = _tok(css, "shell"), _tok(css, "surface"), _tok(css, "text")
        if not (shell and surface and text):
            continue
        compose._SHELL_TEXTSAFE = compose._theme_shell_textsafe(t)  # set the per-frame global as compose_frame does
        page_bg = shell if compose._page_bg() == "var(--shell)" else surface
        c = _contrast(text, page_bg)
        if c < 3.0:
            bad.append(f"{t}: --text on page-bg {page_bg} = {c:.1f}:1")
    assert not bad, "page-bg illegible (a block full-bleed ground would be unreadable): " + "; ".join(bad)


# Text that renders DIRECTLY over the page GROUND (_page_bg) — NOT inside a card/pill (own background) or
# behind a scrim — must take its COLOUR and FONT from theme tokens. A hardcoded near-white (#fff) or
# near-black goes invisible the moment a theme flips the ground polarity (the .doc-title #fff-on-a-light-
# theme bug). ADD your class here when a NEW compose.py block paints text straight onto the page ground.
ON_GROUND_TEXT = ["doc-title", "doc-kick"]


def test_on_ground_text_uses_theme_tokens():
    """On-ground text must use var(--text*) colour + var(--font-*) family — else it breaks on a theme whose
    ground is the opposite polarity (the light-theme document-title invisibility bug). Guards the regression
    and documents the rule for future blocks (extend ON_GROUND_TEXT)."""
    bad = []
    for cls in ON_GROUND_TEXT:
        m = re.search(rf"\.{re.escape(cls)}\s*\{{([^}}]*)\}}", COMPOSE_SRC)
        assert m, f".{cls} not found in compose.py CSS"
        body = m.group(1)
        cm = re.search(r"(?<![-\w])color:\s*([^;]+)", body)
        if not cm or "var(--" not in cm.group(1):
            bad.append(f".{cls} colour = {cm.group(1).strip() if cm else '(none)'} — must be var(--text*)")
        fm = re.search(r"font-family:\s*([^;]+)", body)
        if fm and "var(--" not in fm.group(1):
            bad.append(f".{cls} font = {fm.group(1).strip()} — must be var(--font-*)")
    assert not bad, "on-ground text hardcodes a polarity-specific token: " + "; ".join(bad)
