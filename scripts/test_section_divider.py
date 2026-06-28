#!/usr/bin/env python3
"""Test Section Divider template."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import SectionDividerRenderer


def main():
    output_dir = project_root / "test_output" / "dividers"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Section Divider Template Tests")
    print("=" * 60)

    # Test 1: Simple style
    print("\n[1/4] SectionDividerRenderer (simple)...")
    renderer = SectionDividerRenderer(
        title="The Beginning",
        style="simple"
    )
    renderer.render(str(output_dir / "01_divider_simple.mp4"), duration=4.0)
    print("  [OK] Created 01_divider_simple.mp4")

    # Test 2: Numbered style
    print("\n[2/4] SectionDividerRenderer (numbered)...")
    renderer = SectionDividerRenderer(
        title="The Collapse",
        section_number="Part II",
        subtitle="2014 - 2018",
        style="numbered"
    )
    renderer.render(str(output_dir / "02_divider_numbered.mp4"), duration=4.0)
    print("  [OK] Created 02_divider_numbered.mp4")

    # Test 3: Dramatic style
    print("\n[3/4] SectionDividerRenderer (dramatic)...")
    renderer = SectionDividerRenderer(
        title="The End",
        section_number="Chapter 5",
        style="dramatic"
    )
    renderer.render(str(output_dir / "03_divider_dramatic.mp4"), duration=4.0)
    print("  [OK] Created 03_divider_dramatic.mp4")

    # Test 4: Minimal style
    print("\n[4/4] SectionDividerRenderer (minimal)...")
    renderer = SectionDividerRenderer(
        title="Conclusion",
        style="minimal"
    )
    renderer.render(str(output_dir / "04_divider_minimal.mp4"), duration=4.0)
    print("  [OK] Created 04_divider_minimal.mp4")

    print("\n" + "=" * 60)
    print("All Section Divider tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
