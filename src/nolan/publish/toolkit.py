"""Deterministic render toolchain for the publisher (no LLM).

Thin Python wrappers over the beautiful-article skill's render scripts (reacticle
scaffold + build + brand/font/figure), run in WSL via `_shell`; screenshots/PDF
use Windows Chrome directly. The skill is the single source of truth for the
scaffold-template + figure library + scripts (it must be self-contained to load
standalone as a Claude Code skill); this module just orchestrates it. These are
the parts that are pure functions of the workspace — fully unit-testable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import _shell

# Canonical webkit = the beautiful-article skill (same dir `builder.SKILL` points at).
SKILL = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "beautiful-article"
SCRIPTS = SKILL / "scripts"


def _w(p) -> str:
    return _shell.to_wsl_path(p)


def _win(p) -> str:
    """Windows-style path for Chrome (D:/a/b)."""
    s = str(Path(p))
    return s.replace("\\", "/")


def scaffold(workspace: Path, theme: str, cover: bool = True, timeout: int = 1800) -> Path:
    """Create a reacticle workspace at `workspace` (npm install + figures + English UI)."""
    workspace = Path(workspace).resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    flag = "" if cover else " --no-cover"
    # run from the parent and pass the basename, so relative/absolute don't nest.
    cmd = f"bash {_w(SCRIPTS / 'scaffold.sh')} ./{workspace.name} --theme={theme}{flag}"
    _shell.run(cmd, cwd=workspace.parent, timeout=timeout, check=True)
    return workspace


def _ensure_import(workspace: Path, css: str) -> None:
    """Ensure `import "./<css>";` follows reacticle/styles.css in main.tsx."""
    main = Path(workspace) / "article" / "main.tsx"
    txt = main.read_text(encoding="utf-8")
    line = f'import "./{css}";'
    if line in txt:
        return
    anchor = 'import "reacticle/styles.css";'
    txt = txt.replace(anchor, anchor + "\n" + line, 1)
    main.write_text(txt, encoding="utf-8")


def embed_fonts(workspace: Path, css_url: str, timeout: int = 300) -> Path:
    out = Path(workspace) / "article" / "fonts.css"
    cmd = (
        f"python3 {_w(SCRIPTS / 'embed-theme-fonts.py')} "
        f"--css-url {css_url!r} --out article/fonts.css"
    )
    _shell.run(cmd, cwd=workspace, timeout=timeout, check=True)
    _ensure_import(workspace, "fonts.css")
    return out


def brand_recolor(workspace: Path, theme: str, color: str, mode: str = "light") -> Path:
    out = Path(workspace) / "article" / "brand.css"
    cmd = (
        f"node {_w(SCRIPTS / 'brand-theme.mjs')} "
        f"--theme {theme} --color {color!r} --mode {mode} --out article/brand.css"
    )
    _shell.run(cmd, cwd=workspace, timeout=120, check=True)
    _ensure_import(workspace, "brand.css")
    return out


def add_figure(workspace: Path, item: str, timeout: int = 600) -> None:
    """Install an on-demand registry figure (figure-mermaid / figure-chart)."""
    cmd = f"node {_w(SCRIPTS / 'add-figure.mjs')} {item}"
    _shell.run(cmd, cwd=workspace, timeout=timeout, check=True)


def typecheck(workspace: Path) -> _shell.ShellResult:
    return _shell.run("node node_modules/typescript/bin/tsc --noEmit", cwd=workspace, timeout=300)


def build(workspace: Path, timeout: int = 600) -> Path:
    """Typecheck + vite build -> dist/index.html (self-contained, offline)."""
    tc = typecheck(workspace)
    if not tc.ok:
        raise _shell.ShellError("tsc --noEmit", tc)
    _shell.run("node node_modules/vite/bin/vite.js build", cwd=workspace, timeout=timeout, check=True)
    out = Path(workspace) / "dist" / "index.html"
    if not out.exists():
        raise RuntimeError(f"build produced no {out}")
    return out


def deliver(workspace: Path) -> Path:
    """Copy the built single-file HTML to article/article.html (the deliverable)."""
    dist = Path(workspace) / "dist" / "index.html"
    out = Path(workspace) / "article" / "article.html"
    out.write_bytes(dist.read_bytes())
    return out


def is_offline(html_path: Path) -> bool:
    """True if the HTML has no external resource loads (script src / link href / url(http))."""
    import re

    txt = Path(html_path).read_text(encoding="utf-8", errors="replace")
    return not re.search(r'<script[^>]*src="https?://|<link[^>]*href="https?://|url\(https?://', txt)


def screenshot(workspace: Path, out_png: Path, width: int = 1240, height: int = 2400,
               virtual_time_ms: int = 0, timeout: int = 90) -> Path:
    """Render dist/index.html to a PNG with Windows headless Chrome."""
    chrome = _shell.chrome_exe()
    if not chrome:
        raise RuntimeError("no Chrome/Edge found for screenshots")
    ws = Path(workspace)
    url = "file:///" + _win(ws / "dist" / "index.html")
    prof = _win(ws / "dist" / "_shot_profile")
    args = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            f"--user-data-dir={prof}", f"--window-size={width},{height}",
            f"--screenshot={_win(out_png)}"]
    if virtual_time_ms:
        args.insert(1, f"--virtual-time-budget={virtual_time_ms}")
    args.append(url)
    subprocess.run(args, capture_output=True, timeout=timeout)
    if not Path(out_png).exists():
        raise RuntimeError(f"screenshot failed: {out_png}")
    return Path(out_png)


def make_pdf(workspace: Path, out_pdf: Path, timeout: int = 120) -> Path:
    chrome = _shell.chrome_exe()
    if not chrome:
        raise RuntimeError("no Chrome/Edge found for PDF")
    url = "file:///" + _win(Path(workspace) / "dist" / "index.html")
    prof = _win(Path(workspace) / "dist" / "_pdf_profile")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={prof}", "--no-pdf-header-footer",
                    f"--print-to-pdf={_win(out_pdf)}", url], capture_output=True, timeout=timeout)
    if not Path(out_pdf).exists():
        raise RuntimeError(f"pdf failed: {out_pdf}")
    return Path(out_pdf)
