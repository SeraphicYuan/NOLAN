"""Showcase routes for the NOLAN hub.

Moved verbatim from ``nolan.hub.create_hub_app`` (hub split). ``register(app,
ctx)`` unpacks the shared hub context into locals with the original closure
names, then registers the routes unchanged.
"""

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, FileResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir

    # ==================== Showcase Routes ====================
    # The showcase is a read-only gallery of the authorable motion/block
    # vocabulary (built from the registries). The old render-service preset
    # catalog + its live "generate" proxy were removed with Motion-Canvas
    # (2026-07); previews are pre-rendered clips served by /showcase/preview.

    showcase_template = templates_dir / "showcase.html"

    @app.get("/showcase", response_class=HTMLResponse)
    async def showcase_home():
        """Serve the showcase page."""
        return showcase_template.read_text(encoding="utf-8")

    @app.get("/api/showcase/effects")
    async def showcase_list_effects(category: Optional[str] = None, kind: Optional[str] = None):
        """List the AUTHORABLE motion/block vocabulary from the live registries.

        This is a view of what the pipeline can actually author (motion
        registry + block templates) — not the old render-service preset
        catalog. See nolan.webui.showcase_catalog.
        """
        from nolan.webui.showcase_catalog import build_showcase_catalog
        cat = build_showcase_catalog(ctx.repo_root)
        if category and category != "all":
            cat["effects"] = [e for e in cat["effects"] if e["category"] == category]
        if kind and kind != "all":
            cat["effects"] = [e for e in cat["effects"] if e["kind"] == kind]
        return cat

    @app.get("/api/showcase/effects/{effect_id}")
    async def showcase_get_effect(effect_id: str):
        """Get one effect's full detail from the registries."""
        from nolan.webui.showcase_catalog import build_showcase_catalog
        cat = build_showcase_catalog(ctx.repo_root)
        for e in cat["effects"]:
            if e["id"] == effect_id:
                return e
        raise HTTPException(status_code=404, detail="Effect not found")

    @app.get("/showcase/preview/{filename:path}")
    async def showcase_preview(filename: str):
        """Serve a pre-rendered preview clip for a catalog entry."""
        path = ctx.repo_root / "render-service" / "public" / "previews" / filename
        if path.exists():
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="Preview not found")
