#!/usr/bin/env python3
"""Test the Python Template Engine integration."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.scenes import ScenePlan
from nolan.visual_router import VisualRouter, PYTHON_TEMPLATE_TYPES
from nolan.renderer import PythonTemplateEngine


def main():
    print("="*60)
    print("Python Template Engine Integration Test")
    print("="*60)

    # Load Venezuela scene plan
    scene_plan_path = Path(__file__).parent.parent / "projects" / "venezuela" / "scene_plan.json"
    plan = ScenePlan.load(str(scene_plan_path))

    print(f"\nLoaded scene plan: {scene_plan_path}")
    print(f"Python renderable types: {PYTHON_TEMPLATE_TYPES}")

    # Initialize engine
    engine = PythonTemplateEngine()

    # Find scenes the Python engine can render
    renderable_scenes = []
    for section_name, scenes in plan.sections.items():
        for scene in scenes:
            if engine.can_render(scene):
                scene_type = engine.detect_scene_type(scene)
                renderable_scenes.append((section_name, scene, scene_type))

    print(f"\nScenes Python engine can render: {len(renderable_scenes)}")
    print("-"*60)

    for section, scene, scene_type in renderable_scenes[:10]:  # Show first 10
        print(f"  [{section}] {scene.id}")
        print(f"    visual_type: {scene.visual_type}")
        print(f"    detected_type: {scene_type}")
        print(f"    narration: {scene.narration_excerpt[:50]}...")
        print()

    # Test rendering a few scenes
    output_dir = Path(__file__).parent.parent / "test_output" / "python_engine"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("Rendering test scenes...")
    print("="*60)

    # Pick 3 diverse scenes to test
    test_scenes = renderable_scenes[:3]

    for section, scene, scene_type in test_scenes:
        print(f"\n[Rendering] {scene.id} as {scene_type}...")
        result = engine.render(scene, output_dir, duration=5.0)

        if result.success:
            print(f"  [OK] Success: {result.output_path}")
            print(f"       Renderer: {result.renderer_used}")
        else:
            print(f"  [FAIL] {result.error}")

    print("\n" + "="*60)
    print("Integration test complete!")
    print(f"Output directory: {output_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
