#!/usr/bin/env python3
"""Test all Python renderers including new ones."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    QuoteRenderer,
    TitleRenderer,
    StatisticRenderer,
    ListRenderer,
    LowerThirdRenderer,
    CounterRenderer,
    ComparisonRenderer,
    TimelineRenderer,
    TimelineEvent,
    Position,
    POSITIONS,
)


def main():
    output_dir = project_root / "test_output" / "all_renderers"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("NOLAN Python Renderer - Full Test Suite")
    print("="*60)
    print(f"\nAvailable position presets: {list(POSITIONS.keys())}")

    # Test 1: Quote with position
    print("\n[1/8] QuoteRenderer...")
    renderer = QuoteRenderer(
        quote="WE ARE TIRED",
        attribution="- Maria Rodriguez, Caracas"
    )
    renderer.render(str(output_dir / "01_quote.mp4"), duration=5.0)

    # Test 2: Title
    print("\n[2/8] TitleRenderer...")
    renderer = TitleRenderer(
        title="VENEZUELA",
        subtitle="The Price of Oil"
    )
    renderer.render(str(output_dir / "02_title.mp4"), duration=5.0)

    # Test 3: Statistic
    print("\n[3/8] StatisticRenderer...")
    renderer = StatisticRenderer(
        value="1976",
        label="NATIONALIZATION"
    )
    renderer.with_historical_style()
    renderer.render(str(output_dir / "03_statistic.mp4"), duration=5.0)

    # Test 4: List
    print("\n[4/8] ListRenderer...")
    renderer = ListRenderer(
        title="THE VENEZUELAN PARADOX",
        items=["History", "Economy", "Politics"]
    )
    renderer.render(str(output_dir / "04_list.mp4"), duration=6.0)

    # Test 5: Lower Third
    print("\n[5/8] LowerThirdRenderer...")
    renderer = LowerThirdRenderer(
        name="Maria Rodriguez",
        title="Caracas Resident"
    )
    renderer.render(str(output_dir / "05_lower_third.mp4"), duration=4.0)

    # Test 6: Counter
    print("\n[6/8] CounterRenderer...")
    renderer = CounterRenderer(
        value=300,
        label="BILLION BARRELS OF OIL",
        suffix=""
    )
    renderer.render(str(output_dir / "06_counter.mp4"), duration=5.0)

    # Test 7: Comparison
    print("\n[7/8] ComparisonRenderer...")
    renderer = ComparisonRenderer(
        left_text="Maduro",
        right_text="Guaido",
        left_subtitle="Current President",
        right_subtitle="Opposition Leader"
    )
    renderer.render(str(output_dir / "07_comparison.mp4"), duration=5.0)

    # Test 8: Timeline
    print("\n[8/8] TimelineRenderer...")
    renderer = TimelineRenderer(
        title="KEY DATES",
        events=[
            TimelineEvent("1821", "Independence"),
            TimelineEvent("1976", "Oil Nationalization"),
            TimelineEvent("1998", "Chavez Elected"),
            TimelineEvent("2014", "Economic Crisis"),
        ]
    )
    renderer.render(str(output_dir / "08_timeline.mp4"), duration=8.0)

    print("\n" + "="*60)
    print("All renderer tests completed!")
    print(f"Output directory: {output_dir}")
    print("="*60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
