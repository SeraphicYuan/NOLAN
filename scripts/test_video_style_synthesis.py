"""Test: video-style synthesis brief + analyze_video_style wiring (no model/db).

Usage:
    D:/env/nolan/python.exe scripts/test_video_style_synthesis.py
"""

import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.video_style.tasks import video_style_synthesis_task


def main():
    task = video_style_synthesis_task("cold-data", "Cold Data Explainer", ["vid-a", "vid-b"])
    print(task[:280])
    for needle in [
        "video_styles/cold-data/per_video/*.json",
        "video_styles/cold-data/frames/<slug>",
        "video_styles/cold-data/video_style_guide.md",
        "Script ↔ Visual Pairing",     # the key section
        "Color & Lighting", "Editing & Pacing", "Cinematography",
        "Motion Graphics & Text", "distribution", "said↔shown",
        "(2 files)",
    ]:
        assert needle in task, f"brief missing: {needle!r}"
    print("synthesis brief OK (sections + pairing emphasis + paths + count)")

    # op wiring: importable, async, right params, no model/db touched here
    from src.nolan.webui import operations
    assert inspect.iscoroutinefunction(operations.analyze_video_style), "must be async"
    params = set(inspect.signature(operations.analyze_video_style).parameters)
    for p in ("config", "store_root", "db_path", "style_id", "session", "enable_vision"):
        assert p in params, f"missing param {p}"
    assert hasattr(operations, "_vseg_to_dict")
    print("analyze_video_style wiring OK")
    print("\nOK - synthesis task + op verified.")


if __name__ == "__main__":
    main()
