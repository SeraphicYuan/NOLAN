"""Tests for the viewer server."""

import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient

from nolan.viewer import create_app


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project directory."""
    # Create script
    (tmp_path / "script.md").write_text("""# Video Script

**Total Duration:** 2:30

---

## Hook [0:00 - 0:45]

Venezuela. A land of stunning beauty.
""")

    # Create scene plan
    scene_plan = {
        "sections": {
            "Hook": [
                {
                    "id": "scene_001",
                    "start": "0:00",
                    "duration": "15s",
                    "narration_excerpt": "Venezuela. A land",
                    "visual_type": "b-roll",
                    "visual_description": "Aerial view of Venezuela",
                    "search_query": "venezuela aerial",
                    "comfyui_prompt": "aerial view venezuela",
                    "library_match": True,
                    "skip_generation": False,
                    "matched_asset": None,
                    "generated_asset": None
                }
            ]
        }
    }
    (tmp_path / "scene_plan.json").write_text(json.dumps(scene_plan))

    # Create asset directories
    (tmp_path / "assets" / "generated").mkdir(parents=True)
    (tmp_path / "assets" / "matched").mkdir(parents=True)

    return tmp_path


def test_viewer_serves_index(sample_project):
    """Viewer serves the index page."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_viewer_serves_script(sample_project):
    """Viewer serves the script content."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/api/script")

    assert response.status_code == 200
    assert "Venezuela" in response.json()["content"]


def test_viewer_serves_scene_plan(sample_project):
    """Viewer serves the scene plan."""
    app = create_app(sample_project)
    client = TestClient(app)

    response = client.get("/api/scenes")

    assert response.status_code == 200
    assert "Hook" in response.json()["sections"]
