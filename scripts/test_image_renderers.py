#!/usr/bin/env python3
"""Test KenBurns and Flashback renderers with actual images."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import KenBurnsRenderer, FlashbackRenderer


def main():
    output_dir = project_root / "test_output" / "image_renderers"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find a test image
    scratch_broll = project_root / ".scratch" / "test_output" / "assets" / "broll"
    test_images = list(scratch_broll.glob("*.jpg"))

    if not test_images:
        print("No test images found in .scratch/test_output/assets/broll/")
        print("Creating a test image...")
        # Create a simple gradient image for testing
        from PIL import Image, ImageDraw
        test_img = Image.new('RGB', (1920, 1080), (40, 60, 100))
        draw = ImageDraw.Draw(test_img)
        # Draw some shapes for visual interest
        for i in range(0, 1920, 100):
            draw.line([(i, 0), (i, 1080)], fill=(60, 80, 120), width=2)
        for i in range(0, 1080, 100):
            draw.line([(0, i), (1920, i)], fill=(60, 80, 120), width=2)
        # Add a central focal point
        draw.ellipse([760, 440, 1160, 640], fill=(200, 150, 100))
        test_image_path = output_dir / "test_image.jpg"
        test_img.save(test_image_path)
        print(f"Created test image: {test_image_path}")
    else:
        test_image_path = test_images[0]
        print(f"Using test image: {test_image_path}")

    print("=" * 60)
    print("NOLAN Image Renderer Tests")
    print("=" * 60)

    # Test 1: Ken Burns - Zoom In
    print("\n[1/5] KenBurnsRenderer (zoom in)...")
    renderer = KenBurnsRenderer(
        image_path=str(test_image_path),
        zoom_start=1.0,
        zoom_end=1.3,
        pan_direction=None,  # Just zoom, no pan
    )
    renderer.render(str(output_dir / "01_kenburns_zoom_in.mp4"), duration=5.0)
    print("  [OK] Created 01_kenburns_zoom_in.mp4")

    # Test 2: Ken Burns - Zoom Out
    print("\n[2/5] KenBurnsRenderer (zoom out)...")
    renderer = KenBurnsRenderer(
        image_path=str(test_image_path),
        zoom_start=1.3,
        zoom_end=1.0,
        pan_direction=None,
    )
    renderer.render(str(output_dir / "02_kenburns_zoom_out.mp4"), duration=5.0)
    print("  [OK] Created 02_kenburns_zoom_out.mp4")

    # Test 3: Ken Burns - Pan with Zoom
    print("\n[3/5] KenBurnsRenderer (pan right + zoom)...")
    renderer = KenBurnsRenderer(
        image_path=str(test_image_path),
        zoom_start=1.1,
        zoom_end=1.2,
        pan_direction="right",
        pan_amount=0.15,
    )
    renderer.render(str(output_dir / "03_kenburns_pan_zoom.mp4"), duration=5.0)
    print("  [OK] Created 03_kenburns_pan_zoom.mp4")

    # Test 4: Flashback - Sepia
    print("\n[4/5] FlashbackRenderer (sepia)...")
    renderer = FlashbackRenderer(
        image_path=str(test_image_path),
        style="sepia",
        vignette=True,
        grain=0.05,
        year_text="1976",
    )
    renderer.render(str(output_dir / "04_flashback_sepia.mp4"), duration=5.0)
    print("  [OK] Created 04_flashback_sepia.mp4")

    # Test 5: Flashback - Black & White
    print("\n[5/5] FlashbackRenderer (black & white)...")
    renderer = FlashbackRenderer(
        image_path=str(test_image_path),
        style="bw",
        vignette=True,
        grain=0.08,
        year_text="1821",
    )
    renderer.render(str(output_dir / "05_flashback_bw.mp4"), duration=5.0)
    print("  [OK] Created 05_flashback_bw.mp4")

    print("\n" + "=" * 60)
    print("All image renderer tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
