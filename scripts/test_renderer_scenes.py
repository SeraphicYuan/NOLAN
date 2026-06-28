#!/usr/bin/env python3
"""Test the NOLAN renderer with real scenes from the Venezuela project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nolan.renderer import QuoteRenderer, TitleRenderer, StatisticRenderer
from nolan.renderer.presets import big_number, historical_year, chapter_title, documentary_title


def main():
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    print("="*60)
    print("NOLAN Renderer - Venezuela Scene Tests")
    print("="*60)

    # Test 1: Big statistic - Oil reserves (Hook scene_006)
    # "all of this is happening in a country sitting on top of one of the world's largest oil reserves"
    print("\n[Test 1] Big Number - Oil Reserves...")
    big_number(
        number="300",
        label="BILLION BARRELS OF OIL RESERVES",
        output_path=str(output_dir / "scene_oil_reserves.mp4"),
        duration=6.0,
        suffix=" BILLION",
        style="modern",
    )

    # Test 2: Year reveal - 1976 Nationalization (Evidence 1 scene_007)
    # "Even in 1976, when the oil industry was nationalized"
    print("\n[Test 2] Year Reveal - 1976 Nationalization...")
    historical_year(
        year="1976",
        label="NATIONALIZATION",
        output_path=str(output_dir / "scene_1976_nationalization.mp4"),
        duration=5.0,
    )

    # Test 3: Chapter title - The Venezuelan Paradox (Thesis scene_002)
    print("\n[Test 3] Chapter Title - Venezuelan Paradox...")
    chapter_title(
        chapter="II",
        title="THE VENEZUELAN PARADOX",
        output_path=str(output_dir / "scene_venezuelan_paradox.mp4"),
        duration=5.0,
    )

    # Test 4: Documentary title with longer subtitle
    print("\n[Test 4] Documentary Title - Full Title Card...")
    documentary_title(
        title="EVIDENCE OF COLLAPSE",
        subtitle="How oil dependency destroyed an economy",
        output_path=str(output_dir / "scene_evidence_title.mp4"),
        duration=6.0,
    )

    # Test 5: Danger-style statistic - Hyperinflation
    print("\n[Test 5] Danger Style - Hyperinflation Rate...")
    renderer = StatisticRenderer(
        value="1,000,000",
        label="PERCENT INFLATION RATE",
        prefix="",
        suffix="%",
        value_size=120,
    )
    renderer.with_danger_style()
    renderer.render(
        str(output_dir / "scene_hyperinflation.mp4"),
        duration=5.0,
    )

    # Test 6: Quote from the conclusion
    print("\n[Test 6] Key Insight Quote...")
    renderer = QuoteRenderer(
        quote="UNDERSTANDING THESE COMPLEXITIES",
        attribution="— is the first step toward finding a way forward",
        quote_size=64,
    )
    renderer.render(
        str(output_dir / "scene_key_insight.mp4"),
        duration=6.0,
    )

    print("\n" + "="*60)
    print("All scene tests completed!")
    print(f"Output directory: {output_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
