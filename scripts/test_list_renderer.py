#!/usr/bin/env python3
"""Test the ListRenderer with the Venezuelan Paradox scene."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nolan.renderer import ListRenderer
from nolan.renderer.presets import topic_list


def main():
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    print("="*60)
    print("ListRenderer Test - Venezuelan Paradox")
    print("="*60)

    # Test 1: The Venezuelan Paradox scene (Thesis scene_002)
    print("\n[Test 1] Venezuelan Paradox - Three Lenses...")
    renderer = ListRenderer(
        title="THE VENEZUELAN PARADOX",
        items=["History", "Economy", "Politics"],
        title_size=80,
        item_size=52,
    )
    renderer.render(
        str(output_dir / "list_venezuelan_paradox.mp4"),
        duration=6.0,
    )

    # Test 2: Using the preset function
    print("\n[Test 2] Topic List Preset...")
    topic_list(
        title="THREE FORCES OF DIVISION",
        items=[
            "Colonial Legacy & Caudillo Era",
            "Oil Dependency & Economic Collapse",
            "Political Fragmentation & Corruption"
        ],
        output_path=str(output_dir / "list_three_forces.mp4"),
        duration=7.0,
    )

    # Test 3: Documentary style with bullets instead of numbers
    print("\n[Test 3] Bullet Points (no numbers)...")
    renderer = ListRenderer(
        title="KEY INSIGHTS",
        items=[
            "Wealth wasn't shared",
            "Oil made economy vulnerable",
            "Corruption accelerated collapse"
        ],
        show_numbers=False,
        title_size=64,
        item_size=44,
        accent_color=(70, 130, 220),  # Blue accent
    )
    renderer.render(
        str(output_dir / "list_key_insights.mp4"),
        duration=6.0,
    )

    # Test 4: Academic style
    print("\n[Test 4] Academic Style...")
    renderer = ListRenderer(
        title="THESIS STRUCTURE",
        items=[
            "Historical Context",
            "Economic Analysis",
            "Political Dynamics",
            "Conclusion"
        ],
        title_size=60,
        item_size=42,
    )
    renderer.with_academic_style()
    renderer.render(
        str(output_dir / "list_academic.mp4"),
        duration=7.0,
    )

    print("\n" + "="*60)
    print("All ListRenderer tests completed!")
    print(f"Output directory: {output_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
