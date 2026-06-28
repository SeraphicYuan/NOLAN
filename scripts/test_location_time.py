#!/usr/bin/env python3
"""Test Location/Time templates."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    LocationStampRenderer,
    ChapterCardRenderer,
    ProgressBarRenderer,
)


def main():
    output_dir = project_root / "test_output" / "location_time"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Location/Time Template Tests")
    print("=" * 60)

    # Test 1: Location Stamp
    print("\n[1/3] LocationStampRenderer...")
    renderer = LocationStampRenderer(
        location="Caracas, Venezuela",
        date="March 15, 2014",
        sublocation="Presidential Palace"
    )
    renderer.render(str(output_dir / "01_location_stamp.mp4"), duration=5.0)
    print("  [OK] Created 01_location_stamp.mp4")

    # Test 1b: Location with coordinates
    print("\n[1b] LocationStampRenderer (with coordinates)...")
    renderer = LocationStampRenderer(
        location="Maracaibo, Venezuela",
        coordinates="10.6317\u00b0 N, 71.6406\u00b0 W",
        position="lower-third-right"
    )
    renderer.render(str(output_dir / "01b_location_coords.mp4"), duration=5.0)
    print("  [OK] Created 01b_location_coords.mp4")

    # Test 2: Chapter Card
    print("\n[2/3] ChapterCardRenderer...")
    renderer = ChapterCardRenderer(
        title="The Rise of a Revolution",
        chapter_number="Chapter 1",
        subtitle="Venezuela 1998-2002"
    )
    renderer.render(str(output_dir / "02_chapter_card.mp4"), duration=5.0)
    print("  [OK] Created 02_chapter_card.mp4")

    # Test 2b: Chapter without number
    print("\n[2b] ChapterCardRenderer (title only)...")
    renderer = ChapterCardRenderer(
        title="The Economic Collapse"
    )
    renderer.render(str(output_dir / "02b_chapter_simple.mp4"), duration=4.0)
    print("  [OK] Created 02b_chapter_simple.mp4")

    # Test 3: Progress Bar
    print("\n[3/3] ProgressBarRenderer...")
    renderer = ProgressBarRenderer(
        progress=0.65,
        label="Story Progress"
    )
    renderer.render(str(output_dir / "03_progress_bar.mp4"), duration=4.0)
    print("  [OK] Created 03_progress_bar.mp4")

    # Test 3b: Progress bar at different values
    print("\n[3b] ProgressBarRenderer (25%)...")
    renderer = ProgressBarRenderer(
        progress=0.25,
        label="Part 1 of 4",
        bar_fill_color=(255, 180, 100)  # Orange
    )
    renderer.render(str(output_dir / "03b_progress_25.mp4"), duration=4.0)
    print("  [OK] Created 03b_progress_25.mp4")

    print("\n" + "=" * 60)
    print("All Location/Time tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
