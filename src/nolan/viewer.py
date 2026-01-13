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

    # Get template paths
    templates_dir = Path(__file__).parent / "templates"
    index_template = templates_dir / "index.html"
    scenes_template = templates_dir / "scenes.html"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the main viewer page."""
        return index_template.read_text()

    @app.get("/scenes", response_class=HTMLResponse)
    async def scenes_view():
        """Serve the scene plan viewer page."""
        if scenes_template.exists():
            return scenes_template.read_text()
        return "<h1>Scene viewer template not found</h1>"

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

    @app.get("/api/scenes/flat")
    async def get_scenes_flat():
        """Get all scenes as a flat list with section info."""
        scene_path = project_dir / "scene_plan.json"
        if not scene_path.exists():
            return {"scenes": [], "sections": []}

        data = json.loads(scene_path.read_text())
        scenes = []
        sections = list(data.get("sections", {}).keys())

        for section_name, section_scenes in data.get("sections", {}).items():
            for scene in section_scenes:
                scene["_section"] = section_name
                scenes.append(scene)

        # Sort by start_seconds if available
        scenes.sort(key=lambda s: s.get("start_seconds") or 0)

        return {"scenes": scenes, "sections": sections}

    @app.get("/api/audio-info")
    async def get_audio_info():
        """Get voiceover audio file info."""
        voiceover_dir = project_dir / "assets" / "voiceover"
        if voiceover_dir.exists():
            for ext in [".mp3", ".wav", ".m4a", ".ogg"]:
                audio_file = voiceover_dir / f"voiceover{ext}"
                if audio_file.exists():
                    return {"path": f"/assets/voiceover/voiceover{ext}", "exists": True}
        return {"path": None, "exists": False}

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
