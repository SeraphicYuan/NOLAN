"""Phase-1 tests for the deterministic publish toolkit (no LLM).

Run: D:\\env\\nolan\\python.exe -m nolan.publish.tests.test_toolkit
(or pytest). Exercises the real WSL build bridge against an existing workspace.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from nolan.publish import source, toolkit

REPO = Path(__file__).resolve().parents[4]
WS = REPO / "beautiful-articles" / "human-3.0-build"   # an existing built workspace
ORIG_HTML = REPO / "beautiful-articles" / "human-3.0" / "source" / "original.html"


def test_source_from_html_file():
    doc = source.load_source(str(ORIG_HTML))
    assert "HUMAN 3.0" in doc.title.upper()
    assert "quadrant" in doc.markdown.lower()
    assert len(doc.markdown) > 2000
    print(f"  source: title={doc.title!r}, {len(doc.markdown)} chars md")


def test_source_slugify():
    assert source.slugify("HUMAN 3.0 — A Map!") == "human-3-0-a-map"


def test_source_raw_text_ok():
    doc = source.load_source("Just some pasted prose.\n\nA second paragraph, no path here.")
    assert doc.title == "Untitled"
    assert "pasted prose" in doc.markdown


def test_source_missing_path_raises():
    # a path-looking src that doesn't resolve must fail loudly, not become body text
    for bad in ("./nope.md", "/tmp/does-not-exist.html", "D:\\x\\y.md"):
        try:
            source.load_source(bad)
        except (FileNotFoundError, ValueError):
            continue
        raise AssertionError(f"expected load_source({bad!r}) to raise, but it returned silently")
    print("  source guard: mistyped paths raise instead of degrading")


def test_build_deliver_offline():
    assert WS.exists(), f"missing test workspace {WS}"
    dist = toolkit.build(WS)
    assert dist.exists() and dist.stat().st_size > 100_000
    out = toolkit.deliver(WS)
    assert out.exists()
    assert toolkit.is_offline(out), "deliverable has external resource loads"
    print(f"  build: {dist.stat().st_size//1024} KB, offline=True")


def test_screenshot():
    png = WS / "dist" / "_test_shot.png"
    if png.exists():
        png.unlink()
    toolkit.screenshot(WS, png, width=900, height=1200)
    assert png.exists() and png.stat().st_size > 5_000
    print(f"  screenshot: {png.stat().st_size//1024} KB")
    png.unlink()


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
