"""One-shot smoke test for the 2026-06 code-review changes.

Automates the parts of the manual checklist that can run headless:
  - static/import checks (deleted modules, counter-renderer mapping, XSS escaping)
  - CLI checks (removed commands gone; `nolan projects status/backfill` run)
  - HTTP checks against a RUNNING hub (unified /api/projects, path-traversal 404,
    pages load)

Render-pipeline behaviors that need a real project (orchestrator select_clips, a
counter scene's pixels, composite_over_broll alpha) are listed at the end as
MANUAL — they can't be exercised generically.

Usage:
    # start the hub first (in another terminal):  nolan hub
    D:\\env\\nolan\\python.exe -X utf8 scripts\\smoke_review.py
    D:\\env\\nolan\\python.exe -X utf8 scripts\\smoke_review.py --url http://127.0.0.1:8011
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

_results: list[tuple[str, str, str]] = []


def ok(name, detail=""): _results.append((name, "PASS", detail))
def bad(name, detail=""): _results.append((name, "FAIL", detail))
def skip(name, detail=""): _results.append((name, "SKIP", detail))


def run(name, fn):
    try:
        fn()
    except AssertionError as e:
        bad(name, str(e))
    except Exception as e:  # noqa: BLE001
        bad(name, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- static / import
def check_deleted_modules():
    dead = ["library_viewer.py", "showcase.py", "viewer.py", "matcher.py"]
    present = [m for m in dead if (REPO / "src" / "nolan" / m).exists()]
    assert not present, f"dead modules still present: {present}"
    ok("Phase B: dead modules removed")


def check_counter_mapping():
    from nolan.orchestrator.render import _build_renderer_registry
    cls = _build_renderer_registry()["counter"]
    assert cls.__name__ == "CounterRenderer", f"counter -> {cls.__name__}"
    assert hasattr(cls, "render"), "counter class has no .render() (would render black)"
    ok("Phase A: orchestrator counter -> CounterRenderer")


def check_xss_escaping():
    tpl = REPO / "src" / "nolan" / "templates"
    for f in ("scenes.html", "script_projects.html"):
        txt = (tpl / f).read_text(encoding="utf-8")
        assert "function esc(" in txt, f"{f} missing esc() helper"
    ok("Phase A: XSS esc() helper present in templates")


def check_alpha_and_clipmatcher():
    from nolan.renderer.base import BaseRenderer
    r = BaseRenderer.__new__(BaseRenderer)
    r.bg_color = (26, 26, 26); r._transparent = True
    assert r._alpha_color((255, 0, 0), 0.0)[3] == 0, "transparent alpha not honored"
    ok("Phase A: renderer transparent alpha")


# ---------------------------------------------------------------- CLI
def _nolan(*args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "nolan", *args],
                          capture_output=True, text=True, cwd=str(REPO), timeout=120)


def check_removed_cli_commands():
    out = _nolan("--help").stdout
    bad_cmds = [c for c in ("serve", "browse", "showcase", "library")
                if f"\n  {c} " in out or f"\n  {c}\n" in out]
    assert not bad_cmds, f"removed commands still in CLI: {bad_cmds}"
    ok("Phase B: serve/browse/showcase/library removed from CLI")


def check_projects_cli():
    r = _nolan("projects", "status")
    assert r.returncode == 0, f"`projects status` exit {r.returncode}: {r.stderr[-300:]}"
    r2 = _nolan("projects", "backfill", "--dry-run")
    assert r2.returncode == 0, f"`projects backfill --dry-run` exit {r2.returncode}"
    ok("C1: `nolan projects status` + `backfill --dry-run` run")


# ---------------------------------------------------------------- HTTP (hub running)
def _client(url):
    import httpx
    return httpx.Client(base_url=url, timeout=15.0)


def check_hub_pages(url):
    pages = ["/", "/scenes", "/library", "/clips", "/images", "/extract",
             "/script-styles", "/script-projects"]
    with _client(url) as c:
        failed = []
        for p in pages:
            try:
                if c.get(p).status_code != 200:
                    failed.append(p)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{p}({type(e).__name__})")
        assert not failed, f"pages not 200: {failed}"
    ok("Hub pages load (8 pages)")


def check_api_projects(url):
    with _client(url) as c:
        data = c.get("/api/projects").json()
    assert "projects" in data and "total" in data, "missing keys"
    assert all("kinds" in p and "library_project_id" in p for p in data["projects"]), \
        "project dicts missing capability fields"
    ok(f"C1: GET /api/projects unified ({data['total']} projects)")
    return data["projects"]


def check_path_traversal(url, projects):
    if not projects:
        skip("Security: path traversal", "no projects to test under (create one first)")
        return
    slug = projects[0]["slug"]
    with _client(url) as c:
        r = c.get(f"/scenes/assets/{slug}/..%2f..%2f..%2fpyproject.toml")
    assert r.status_code != 200, f"traversal returned {r.status_code} (should be 404)"
    assert "[project]" not in r.text and "nolan" not in r.text[:200].lower() or r.status_code == 404
    ok("Security: /scenes/assets path traversal blocked (404)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8011", help="running hub base URL")
    args = ap.parse_args()

    # headless checks
    run("deleted modules", check_deleted_modules)
    run("counter mapping", check_counter_mapping)
    run("xss escaping", check_xss_escaping)
    run("renderer alpha", check_alpha_and_clipmatcher)
    run("cli removed cmds", check_removed_cli_commands)
    run("projects cli", check_projects_cli)

    # HTTP checks (only if hub reachable)
    import httpx
    try:
        httpx.get(args.url + "/api/status", timeout=5.0)
        hub_up = True
    except Exception:
        hub_up = False

    if not hub_up:
        skip("Hub HTTP checks", f"hub not reachable at {args.url} — start it with `nolan hub`")
    else:
        run("hub pages", lambda: check_hub_pages(args.url))
        projects = []
        def _api():
            nonlocal projects
            projects = check_api_projects(args.url)
        run("api/projects", _api)
        run("path traversal", lambda: check_path_traversal(args.url, projects))

    # summary
    print("\n" + "=" * 64)
    width = max(len(n) for n, _, _ in _results)
    for name, status, detail in _results:
        mark = {"PASS": "[ok ]", "FAIL": "[FAIL]", "SKIP": "[skip]"}[status]
        line = f"{mark} {name:<{width}}"
        if detail:
            line += f"  — {detail}"
        print(line)
    n_fail = sum(1 for _, s, _ in _results if s == "FAIL")
    n_pass = sum(1 for _, s, _ in _results if s == "PASS")
    n_skip = sum(1 for _, s, _ in _results if s == "SKIP")
    print("=" * 64)
    print(f"{n_pass} passed, {n_fail} failed, {n_skip} skipped")

    print("\nMANUAL (need a real project / render — not automatable here):")
    print("  - Render a counter/statistic scene via the orchestrator -> not a black frame")
    print("  - Run an orchestrate through select_clips -> no NameError, reaches awaiting_review")
    print("  - composite_over_broll: overlay fades smoothly over b-roll (no grey ghost)")
    print("  - In a browser, create a /script-projects project named "
          "'<img src=x onerror=alert(1)>' -> shows as text, no alert")

    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
