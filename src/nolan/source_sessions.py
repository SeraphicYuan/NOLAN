"""Local credential/session maintenance for acquisition sources.

Secrets never cross a web response and are never printed. The functions in
this module are suitable for both a CLI script and a future localhost-only
source-management route.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode


RAWPIXEL_SEARCH = "https://www.rawpixel.com/api/v1/search"


@dataclass(frozen=True)
class RawpixelSessionRefresh:
    cookie_count: int
    has_session_cookie: bool
    user_agent: str
    search_rows: int
    search_total: int | None
    env_path: Path | None = None
    dry_run: bool = False


def _dotenv_quote(value: str) -> str:
    """Double-quote a dotenv value, including embedded JSON quotes safely."""
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\r", "\\r").replace("\n", "\\n"))
    return f'"{escaped}"'


def update_env_text(text: str, updates: Dict[str, str]) -> str:
    """Replace/append dotenv keys without exposing or reformatting other values."""
    newline = "\r\n" if "\r\n" in text else "\n"
    had_final_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    remaining = dict(updates)
    out = []
    for line in lines:
        stripped = line.lstrip()
        replaced = False
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={_dotenv_quote(remaining.pop(key))}")
                replaced = True
        if not replaced:
            out.append(line)
    if remaining and out and out[-1].strip():
        out.append("")
    out.extend(f"{key}={_dotenv_quote(value)}" for key, value in remaining.items())
    result = newline.join(out)
    if had_final_newline or remaining:
        result += newline
    return result


def write_env_values(path: Path, updates: Dict[str, str]) -> None:
    """Atomically update selected values in an existing project dotenv file."""
    path = Path(path)
    original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    rendered = update_env_text(original, updates)
    temporary = path.with_name(f".{path.name}.rawpixel-session.tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8", newline="")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def refresh_rawpixel_session(*, cdp_url: str = "http://127.0.0.1:9222",
                             env_path: Path | None = None,
                             verify_query: str = "wave",
                             dry_run: bool = False) -> RawpixelSessionRefresh:
    """Capture Rawpixel cookies from authorised Chrome and optionally update `.env`.

    Chrome remains the preferred transport because Cloudflare can reject a
    replayed cookie even when it is fresh. Persisting the cookie is useful as a
    fallback and makes session health visible to a future management surface.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError("Playwright is required to refresh the Rawpixel session") from exc

    os.environ.setdefault("NODE_NO_WARNINGS", "1")
    pw = sync_playwright().start()
    page = None
    try:
        browser = pw.chromium.connect_over_cdp(cdp_url, timeout=15_000)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP has no reusable browser context")
        context = browser.contexts[0]
        page = context.new_page()
        params = {
            "curated_tag": verify_query, "image_type": "image", "keys": verify_query,
            "lang": "en", "page": 1, "published_status": "published",
            "show_creative_brushes": "false", "sort": "curated",
            "tags": "$publicdomain",
        }
        response = page.goto(
            f"{RAWPIXEL_SEARCH}?{urlencode(params)}",
            wait_until="domcontentloaded", timeout=30_000)
        status = response.status if response else 0
        body = page.locator("body").inner_text(timeout=30_000).strip()
        if status != 200:
            raise RuntimeError(f"Rawpixel verification returned HTTP {status}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Rawpixel verification did not return JSON") from exc
        rows = payload.get("results") or []
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("Rawpixel verification returned no search records")

        user_agent = page.evaluate("navigator.userAgent")
        cookies = context.cookies([RAWPIXEL_SEARCH])
        cookies = [c for c in cookies if c.get("domain", "").lstrip(".").endswith("rawpixel.com")]
        has_session = any(c.get("name", "").startswith(("SESS", "SSESS")) for c in cookies)
        if not has_session:
            raise RuntimeError(
                "Chrome can search Rawpixel but has no signed-in session cookie; sign in and retry")
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        target = Path(env_path) if env_path is not None else None
        if target is not None and not dry_run:
            write_env_values(target, {
                "RAWPIXEL_COOKIE": cookie_header,
                "RAWPIXEL_USER_AGENT": str(user_agent),
                "RAWPIXEL_CDP_URL": cdp_url,
            })
        return RawpixelSessionRefresh(
            cookie_count=len(cookies), has_session_cookie=has_session,
            user_agent=str(user_agent), search_rows=len(rows),
            search_total=(int(payload["total"]) if payload.get("total") is not None else None),
            env_path=target, dry_run=dry_run)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Could not refresh Rawpixel from Chrome at {cdp_url}: {exc}") from exc
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        pw.stop()  # detach only; never close the user's Chrome browser
