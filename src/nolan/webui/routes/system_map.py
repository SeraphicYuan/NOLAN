"""The Live NOLAN Map — /map page + /api/map catalog."""

from fastapi.responses import HTMLResponse


def register(app, ctx):
    templates_dir = ctx.templates_dir

    @app.get("/map", response_class=HTMLResponse)
    async def map_page():
        tpl = templates_dir / "map.html"
        if tpl.exists():
            return tpl.read_text(encoding="utf-8")
        return "<h1>map.html not found</h1>"

    @app.get("/api/map")
    async def api_map(ping: bool = True):
        from nolan.system_map import build_map
        return build_map(app=app, ping=ping)
