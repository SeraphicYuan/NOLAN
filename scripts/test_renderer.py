#!/usr/bin/env python3
"""Test the new NOLAN renderer system."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nolan.renderer import QuoteRenderer, TitleRenderer, StatisticRenderer
from nolan.renderer.presets import documentary_quote, documentary_title, historical_year


def main():
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    print("="*60)
    print("NOLAN Renderer System Test")
    print("="*60)

    # Test 1: Quote using new renderer
    print("\n[Test 1] QuoteRenderer...")
    renderer = QuoteRenderer(
        quote="WE ARE TIRED",
        attribution="— Maria Rodriguez, Caracas Resident"
    )
    renderer.render(
        str(output_dir / "test_quote_renderer.mp4"),
        duration=7.0
    )

    # Test 2: Title using preset
    print("\n[Test 2] documentary_title preset...")
    documentary_title(
        title="VENEZUELA: THE PRICE OF OIL",
        subtitle="How a nation with incredible wealth became so fractured",
        output_path=str(output_dir / "test_title_preset.mp4"),
        duration=6.0
    )

    # Test 3: Year reveal using preset
    print("\n[Test 3] historical_year preset...")
    historical_year(
        year="1821",
        label="INDEPENDENCIA",
        output_path=str(output_dir / "test_year_preset.mp4"),
        duration=5.0
    )

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)


if __name__ == "__main__":
    main()
