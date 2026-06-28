#!/usr/bin/env python3
"""
Simple quote video renderer using PIL + moviepy with Quality Protocol.
Uses PIL for text rendering (reliable) and moviepy for video encoding.
"""

import sys
from pathlib import Path

# Add parent to path for nolan imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip, ColorClip
from nolan.quality import QualityProtocol, QAConfig


# Font fallback chain
FONT_FALLBACKS = [
    "C:/Windows/Fonts/arialbd.ttf",  # Arial Bold - preferred
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]


def find_font(fonts: list = None) -> str:
    """Find first available font from list."""
    fonts = fonts or FONT_FALLBACKS
    for f in fonts:
        if Path(f).exists():
            return f
    return fonts[0]  # Return first as fallback


def create_quote_frame(
    quote: str,
    attribution: str,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple = (26, 26, 26),
    text_color: str = "white",
    font: str = None,
    font_size: int = 80,
) -> Image.Image:
    """
    Create a single frame with quote text using PIL.
    This provides reliable text rendering without MoviePy's TextClip issues.
    """
    font = font or find_font()

    # Create image
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        quote_font = ImageFont.truetype(font, font_size)
        attr_font = ImageFont.truetype(font.replace('bd.ttf', '.ttf'), 36)
    except OSError:
        # Fallback
        quote_font = ImageFont.truetype(find_font(), font_size)
        attr_font = ImageFont.truetype(find_font(), 36)

    # Draw main quote - centered
    bbox = draw.textbbox((0, 0), quote, font=quote_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2 - 40  # Slightly above center

    draw.text((x, y), quote, fill=text_color, font=quote_font)

    # Draw attribution - centered below quote
    attr_bbox = draw.textbbox((0, 0), attribution, font=attr_font)
    attr_width = attr_bbox[2] - attr_bbox[0]
    attr_x = (width - attr_width) // 2
    attr_y = int(height * 0.62)

    draw.text((attr_x, attr_y), attribution, fill=(136, 136, 136), font=attr_font)

    # Draw red accent bar at bottom
    bar_y = height - 108
    draw.rectangle([(0, bar_y), (width, bar_y + 8)], fill=(220, 38, 38))

    return img


def create_quote_video(
    quote: str,
    attribution: str,
    output_path: str,
    duration: float = 7.0,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple = (26, 26, 26),
    text_color: str = "white",
    font: str = None,
    font_size: int = 80,
) -> str:
    """
    Create a quote video using PIL for text (reliable) and moviepy for encoding.
    """
    print(f"Creating quote video: \"{quote}\"")
    print(f"Using font: {font or find_font()}")

    # Create the quote frame using PIL
    frame = create_quote_frame(
        quote=quote,
        attribution=attribution,
        width=width,
        height=height,
        bg_color=bg_color,
        text_color=text_color,
        font=font,
        font_size=font_size,
    )

    # Convert PIL image to numpy array for moviepy
    frame_array = np.array(frame)

    # Create video from static frame
    clip = ImageClip(frame_array, duration=duration)

    # Write video
    print(f"Rendering to {output_path}...")
    clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=4,
    )

    print(f"Done! Video saved to: {output_path}")
    return output_path


def render_with_quality_check(
    quote: str,
    attribution: str,
    output_path: str,
    duration: float = 7.0,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """
    Render video with Quality Protocol validation.
    """
    print("\n" + "="*60)
    print("NOLAN Quality Protocol - Render with Validation")
    print("="*60 + "\n")

    # Configure QA
    config = QAConfig(
        check_properties=True,
        check_visual=True,
        check_text=False,  # OCR disabled
        duration_tolerance=0.5,
        fallback_fonts=FONT_FALLBACKS,
    )
    qa = QualityProtocol(config)

    # Render video
    print("[QA] Rendering with PIL text (reliable method)...")
    result_path = create_quote_video(
        quote=quote,
        attribution=attribution,
        output_path=output_path,
        duration=duration,
        width=width,
        height=height,
    )

    # Validate
    print("\n[QA] Running validation checks...")
    qa_result = qa.validate(
        video_path=result_path,
        expected_duration=duration,
        expected_resolution=(width, height),
    )

    print(f"\n{qa_result.summary()}")

    if qa_result.passed:
        print(f"\n[QA] SUCCESS - Video passed all quality checks!")
    else:
        print(f"\n[QA] WARNING - Some checks failed (see above)")

    print(f"[QA] Output: {result_path}")
    return result_path


def main():
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    output_path = str(output_dir / "venezuela_we_are_tired_final.mp4")

    # Use quality-checked render
    render_with_quality_check(
        quote="WE ARE TIRED",
        attribution="— Maria Rodriguez, Caracas Resident",
        output_path=output_path,
        duration=7.0,
    )


if __name__ == "__main__":
    main()
