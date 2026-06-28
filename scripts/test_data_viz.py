#!/usr/bin/env python3
"""Test Data Visualization templates."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    StatComparisonRenderer,
    PercentageBarRenderer,
    RankingRenderer,
)


def main():
    output_dir = project_root / "test_output" / "data_viz"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Data Visualization Template Tests")
    print("=" * 60)

    # Test 1: Stat Comparison
    print("\n[1/3] StatComparisonRenderer...")
    renderer = StatComparisonRenderer(
        left_value="$100B",
        left_label="GDP 2012",
        right_value="$12B",
        right_label="GDP 2020",
        title="Economic Collapse"
    )
    renderer.render(str(output_dir / "01_stat_comparison.mp4"), duration=6.0)
    print("  [OK] Created 01_stat_comparison.mp4")

    # Test 1b: Stat Comparison - before/after
    print("\n[1b] StatComparisonRenderer (before/after)...")
    renderer = StatComparisonRenderer(
        left_value="2.5M",
        left_label="Barrels/Day 2008",
        right_value="0.3M",
        right_label="Barrels/Day 2020",
        divider_text="\u2192",  # Arrow
        title="Oil Production Collapse"
    )
    renderer.render(str(output_dir / "01b_stat_beforeafter.mp4"), duration=6.0)
    print("  [OK] Created 01b_stat_beforeafter.mp4")

    # Test 2: Percentage Bar
    print("\n[2/3] PercentageBarRenderer...")
    renderer = PercentageBarRenderer(
        percentage=87,
        label="Population in Poverty",
        context="As of 2020"
    )
    renderer.render(str(output_dir / "02_percentage_bar.mp4"), duration=5.0)
    print("  [OK] Created 02_percentage_bar.mp4")

    # Test 2b: Percentage Bar - different color
    print("\n[2b] PercentageBarRenderer (custom color)...")
    renderer = PercentageBarRenderer(
        percentage=95,
        label="Export Revenue from Oil",
        bar_fill_color=(100, 180, 255)  # Blue
    )
    renderer.render(str(output_dir / "02b_percentage_blue.mp4"), duration=5.0)
    print("  [OK] Created 02b_percentage_blue.mp4")

    # Test 3: Ranking
    print("\n[3/3] RankingRenderer...")
    renderer = RankingRenderer(
        title="Worst Inflation Rates (All Time)",
        items=[
            ("Hungary 1946", "41.9 quadrillion %"),
            ("Zimbabwe 2008", "79.6 billion %"),
            ("Venezuela 2018", "1,698,488%"),
            ("Yugoslavia 1994", "313 million %"),
            ("Germany 1923", "29,500%"),
        ]
    )
    renderer.render(str(output_dir / "03_ranking.mp4"), duration=7.0)
    print("  [OK] Created 03_ranking.mp4")

    # Test 3b: Ranking - simple list
    print("\n[3b] RankingRenderer (simple)...")
    renderer = RankingRenderer(
        title="Key Factors",
        items=[
            ("Oil Price Collapse", "$100 \u2192 $30/barrel"),
            ("Nationalization", "2,000+ companies"),
            ("Currency Controls", "Black market rate"),
        ]
    )
    renderer.render(str(output_dir / "03b_ranking_simple.mp4"), duration=5.0)
    print("  [OK] Created 03b_ranking_simple.mp4")

    print("\n" + "=" * 60)
    print("All Data Visualization tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
