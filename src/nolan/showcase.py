"""Motion Effects Showcase for NOLAN."""

import json
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

RENDER_SERVICE_URL = "http://127.0.0.1:3010"


def create_showcase_app(render_service_url: str = RENDER_SERVICE_URL) -> FastAPI:
    """Create the motion effects showcase FastAPI application.

    Args:
        render_service_url: URL of the render service.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NOLAN Motion Effects Showcase")
    template_path = Path(__file__).parent / "templates" / "showcase.html"
    uploads_dir = Path(__file__).parent.parent.parent / "render-service" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def home():
        """Serve the main showcase page."""
        return template_path.read_text(encoding="utf-8")

    @app.get("/api/effects")
    async def list_effects(category: Optional[str] = None):
        """Proxy effects list from render service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{render_service_url}/effects"
                if category:
                    url += f"?category={category}"
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Render service unavailable. Start it with: cd render-service && npm run dev"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/effects/{effect_id}")
    async def get_effect(effect_id: str):
        """Get specific effect details."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/effects/{effect_id}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Effect not found")
            raise HTTPException(status_code=500, detail=str(e))
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.post("/api/upload")
    async def upload_file(file: UploadFile = File(...)):
        """Upload a file for use in effects."""
        import uuid
        ext = Path(file.filename).suffix if file.filename else ".bin"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = uploads_dir / filename

        content = await file.read()
        filepath.write_bytes(content)

        return {
            "filename": filename,
            "path": str(filepath.absolute()),
            "size": len(content),
        }

    @app.post("/api/render")
    async def render_effect(
        effect: str = Form(...),
        params: str = Form(...),
    ):
        """Submit a render job using an effect."""
        try:
            params_dict = json.loads(params)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid params JSON")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{render_service_url}/render",
                    json={"effect": effect, "params": params_dict},
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/render/status/{job_id}")
    async def get_render_status(job_id: str):
        """Get render job status."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/status/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/api/render/result/{job_id}")
    async def get_render_result(job_id: str):
        """Get render job result."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{render_service_url}/render/result/{job_id}")
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Render service unavailable")

    @app.get("/preview/{filename:path}")
    async def serve_preview(filename: str):
        """Serve preview files from render service output."""
        # Try multiple locations for preview files
        locations = [
            Path(__file__).parent.parent.parent / "render-service" / "public" / "previews" / filename,
            Path(__file__).parent.parent.parent / "render-service" / "output" / filename,
        ]
        for path in locations:
            if path.exists():
                return FileResponse(path)
        raise HTTPException(status_code=404, detail="Preview not found")

    @app.get("/output/{filename:path}")
    async def serve_output(filename: str):
        """Serve rendered output files."""
        path = Path(__file__).parent.parent.parent / "render-service" / "output" / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path)

    return app


def run_showcase(host: str = "127.0.0.1", port: int = 8001):
    """Run the showcase server."""
    import uvicorn
    app = create_showcase_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_showcase()
