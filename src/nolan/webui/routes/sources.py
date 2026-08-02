"""Asset Sources control plane: registry, tiers, health and local actions."""
from __future__ import annotations

import asyncio
import ipaddress

from fastapi import Body, HTTPException, Request
from fastapi.responses import HTMLResponse


def _is_loopback_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.casefold() == "localhost"


def register(app, ctx):
    templates_dir = ctx.templates_dir

    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page():
        return (templates_dir / "sources.html").read_text(encoding="utf-8")

    @app.get("/api/sources")
    async def sources_get(request: Request):
        from nolan.config import load_config
        from nolan.imagelib import shared_library
        from nolan.source_control import build_source_rows

        try:
            library = shared_library(scope="global")
        except Exception:
            library = None
        payload = build_source_rows(load_config(), library=library)
        payload["local_actions_allowed"] = _is_loopback_request(request)
        return payload

    @app.post("/api/sources/rawpixel/refresh")
    async def rawpixel_refresh(request: Request, body: dict = Body(default={})):
        if not _is_loopback_request(request):
            raise HTTPException(status_code=403, detail="Session refresh is localhost-only")
        from nolan.config import load_config
        from nolan.source_control import loopback_cdp_url
        from nolan.source_sessions import refresh_rawpixel_session

        config = load_config().image_sources
        try:
            cdp_url = loopback_cdp_url(
                str(body.get("cdp_url") or config.rawpixel_cdp_url or "http://127.0.0.1:9222"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        query = str(body.get("verify_query") or "wave").strip()[:80]
        if not query:
            raise HTTPException(status_code=400, detail="verify_query cannot be empty")
        try:
            result = await asyncio.to_thread(
                refresh_rawpixel_session, cdp_url=cdp_url,
                env_path=ctx.repo_root / ".env", verify_query=query, dry_run=False)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return {
            "ok": True, "cookie_count": result.cookie_count,
            "session_cookie": result.has_session_cookie,
            "search_rows": result.search_rows, "search_total": result.search_total,
            "message": "Rawpixel session refreshed; secret values were not returned.",
        }
