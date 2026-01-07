"""Viewer server for NOLAN."""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles


def create_app(project_dir: Path) -> FastAPI:
    """Create the viewer FastAPI application.

    Args:
        project_dir: Path to the project output directory.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Viewer")
    project_dir = Path(project_dir)

    # Get template path
    template_path = Path(__file__).parent / "templates" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the main viewer page."""
        return template_path.read_text()

    @app.get("/api/script")
    async def get_script():
        """Get the script content."""
        script_path = project_dir / "script.md"
        if script_path.exists():
            return {"content": script_path.read_text()}
        return {"content": "No script found."}

    @app.get("/api/scenes")
    async def get_scenes():
        """Get the scene plan."""
        scene_path = project_dir / "scene_plan.json"
        if scene_path.exists():
            return json.loads(scene_path.read_text())
        return {"sections": {}}

    # Serve asset files
    assets_dir = project_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    return app


def run_server(project_dir: Path, host: str = "127.0.0.1", port: int = 8000):
    """Run the viewer server.

    Args:
        project_dir: Path to project directory.
        host: Server host.
        port: Server port.
    """
    import uvicorn
    import webbrowser

    app = create_app(project_dir)

    # Open browser
    webbrowser.open(f"http://{host}:{port}")

    # Run server
    uvicorn.run(app, host=host, port=port)
