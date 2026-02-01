"""
Test the portrait_reveal template.

This template shows a portrait that slides aside to reveal bullet points -
perfect for introducing historical figures, thinkers, or experts.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.scenes.portrait_reveal import render_portrait_reveal

OUTPUT_DIR = "test_output/portrait_reveal"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_english_style():
    """Test with English text to verify the animation works."""
    print("\n[1/2] Testing English portrait reveal...")

    output = f"{OUTPUT_DIR}/english_reveal.mp4"

    render_portrait_reveal(
        title="Understanding People",
        points=[
            "Only trust actions",
            "Life happens at events",
            "Not just words",
            "Observe patterns",
        ],
        portrait_caption="Alfred Adler",
        portrait_side="left",
        # Timing
        portrait_hold=1.5,
        slide_duration=0.8,
        point_interval=0.7,
        # Styling
        bg_color=(10, 10, 18),
        border_color=(180, 150, 80),
        portrait_bg_color=(50, 50, 60),
        title_color=(200, 170, 100),
        title_size=56,
        point_color=(220, 220, 230),
        point_size=36,
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def test_right_side():
    """Test with portrait on right side."""
    print("\n[2/2] Testing portrait on right side...")

    output = f"{OUTPUT_DIR}/portrait_right.mp4"

    render_portrait_reveal(
        title="Key Insights",
        points=[
            "First important point",
            "Second key concept",
            "Third takeaway",
        ],
        portrait_side="right",
        portrait_hold=1.2,
        bg_color=(15, 15, 25),
        title_color=(100, 180, 220),
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def main():
    print("=" * 60)
    print("TESTING PORTRAIT REVEAL TEMPLATE")
    print("=" * 60)

    test_english_style()
    test_right_side()

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)
    print(f"\nOutput directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
