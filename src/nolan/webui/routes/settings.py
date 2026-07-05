"""Settings routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from urllib.parse import quote
from fastapi import HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse, FileResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir

    # ==================== Settings ====================

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page():
        tpl = templates_dir / "settings.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>settings.html not found</h1>"

    @app.get("/api/settings")
    async def api_settings_get():
        from nolan.config import load_config
        config = load_config()
        return {
            "vision": {
                "provider": config.vision.provider,
                "model": config.vision.model,
                "reasoning_enabled": config.vision.reasoning_enabled,
                "reasoning_max_tokens": config.vision.reasoning_max_tokens,
            },
            "llm": {
                "provider": config.llm.provider,
                "model": config.llm.model,
                "reasoning_enabled": config.llm.reasoning_enabled,
            },
            "keys": {
                "gemini": bool(config.gemini.api_key),
                "openrouter": bool(config.vision.openrouter_api_key),
            },
            "indexing": {"database": config.indexing.database},
        }

    @app.post("/api/settings")
    async def api_settings_set(body: dict = Body(...)):
        """Persist vision settings to nolan.yaml (vision: block)."""
        import yaml
        cfg_path = Path("nolan.yaml")
        data = {}
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        vision = data.get("vision", {}) or {}
        for key in ("provider", "model", "reasoning_enabled", "reasoning_max_tokens"):
            if key in body:
                vision[key] = body[key]
        data["vision"] = vision
        # LLM block (text tasks) — accepts a nested "llm" object in the body.
        if isinstance(body.get("llm"), dict):
            llm = data.get("llm", {}) or {}
            for key in ("provider", "model", "reasoning_enabled"):
                if key in body["llm"]:
                    llm[key] = body["llm"][key]
            data["llm"] = llm
        cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return {"saved": True, "vision": vision, "llm": data.get("llm")}
