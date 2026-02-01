#!/usr/bin/env python3
"""Test PythonTemplateEngine integration with mock scenes."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dataclasses import dataclass
from typing import Optional


@dataclass
class MockScene:
    """Mock Scene object for testing."""
    id: str
    visual_type: str
    visual_description: str = ""
    narration_excerpt: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 5.0
    matched_asset: Optional[str] = None
    generated_asset: Optional[str] = None
    image_path: Optional[str] = None
    # Additional fields expected by router
    lottie_template: Optional[str] = None
    rendered_clip: Optional[str] = None
    infographic: Optional[dict] = None
    comfyui_prompt: Optional[str] = None


def main():
    from nolan.renderer.engine import PythonTemplateEngine
    from nolan.visual_router import VisualRouter, PYTHON_TEMPLATE_TYPES

    output_dir = project_root / "test_output" / "engine_integration"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Python Template Engine Integration Test")
    print("=" * 60)

    print(f"\nPython renderable types: {sorted(PYTHON_TEMPLATE_TYPES)}")

    # Create test scenes for each Python-renderable type
    test_scenes = [
        MockScene(
            id="test_quote",
            visual_type="quote",
            visual_description="Bold text quote appears on screen",
            narration_excerpt="'We are tired of this' said Maria Rodriguez",
        ),
        MockScene(
            id="test_title",
            visual_type="title",
            visual_description="Video title fades in: 'VENEZUELA'",
            narration_excerpt="Venezuela: The Price of Oil",
        ),
        MockScene(
            id="test_statistic",
            visual_type="statistic",
            visual_description="Large number appears: 300 billion",
            narration_excerpt="Venezuela has 300 billion barrels of oil",
        ),
        MockScene(
            id="test_year",
            visual_type="year",
            visual_description="Year 1976 appears dramatically",
            narration_excerpt="In 1976, oil was nationalized",
        ),
        MockScene(
            id="test_list",
            visual_type="list",
            visual_description="'Key Points': 1. History 2. Economy 3. Politics",
            narration_excerpt="We'll cover three main topics",
        ),
        MockScene(
            id="test_lower_third",
            visual_type="lower-third",
            visual_description="Lower third shows: Maria Rodriguez, Caracas Resident",
            narration_excerpt="Maria tells us about daily life",
        ),
        MockScene(
            id="test_counter",
            visual_type="counter",
            visual_description="Counter animates to 7,000,000",
            narration_excerpt="Over 7 million people have fled Venezuela",
        ),
        MockScene(
            id="test_comparison",
            visual_type="comparison",
            visual_description="Split screen showing Maduro vs Guaido",
            narration_excerpt="The conflict between Maduro versus Guaido",
        ),
        MockScene(
            id="test_timeline",
            visual_type="timeline",
            visual_description="Timeline showing: 1821 Independence, 1976 Oil, 1998 Chavez",
            narration_excerpt="Key dates in Venezuelan history",
        ),
    ]

    engine = PythonTemplateEngine()
    router = VisualRouter()

    print(f"\nTesting {len(test_scenes)} scene types...")
    print("-" * 60)

    rendered = 0
    failed = 0

    for scene in test_scenes:
        # Check routing
        decision = router.route(scene)

        # Check if engine can render
        can_render = engine.can_render(scene)
        scene_type = engine.detect_scene_type(scene) if can_render else "N/A"

        print(f"\n{scene.id}:")
        print(f"  visual_type: {scene.visual_type}")
        print(f"  route: {decision.route}")
        print(f"  can_render: {can_render}")
        print(f"  detected_type: {scene_type}")

        if can_render:
            result = engine.render(scene, output_dir, duration=4.0)
            if result.success:
                print(f"  [OK] Rendered: {Path(result.output_path).name}")
                rendered += 1
            else:
                print(f"  [FAIL] Error: {result.error}")
                failed += 1
        else:
            print(f"  [SKIP] Cannot render this scene type")

    print("\n" + "=" * 60)
    print(f"Results: {rendered} rendered, {failed} failed")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List generated files
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
