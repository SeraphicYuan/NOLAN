#!/usr/bin/env python3
"""
Title card renderer with Quality Protocol.
Creates dramatic title cards for documentary videos using PIL + moviepy.
"""

import sys
from pathlib import Path

# Add parent to path for nolan imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import ImageClip, concatenate_videoclips, CompositeVideoClip
from nolan.quality import QualityProtocol, QAConfig


# Font options
FONTS = {
    "title": "C:/Windows/Fonts/arialbd.ttf",      # Bold for main title
    "subtitle": "C:/Windows/Fonts/arial.ttf",     # Regular for subtitle
    "accent": "C:/Windows/Fonts/georgiab.ttf",    # Georgia Bold for emphasis
}


def find_font(font_type: str = "title") -> str:
    """Find available font."""
    font_path = FONTS.get(font_type, FONTS["title"])
    if Path(font_path).exists():
        return font_path
    return "C:/Windows/Fonts/arial.ttf"


def create_title_frame(
    title: str,
    subtitle: str = None,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple = (15, 15, 20),      # Near black
    title_color: str = "white",
    accent_color: tuple = (220, 38, 38),  # Red
    title_size: int = 90,
    subtitle_size: int = 32,
) -> Image.Image:
    """
    Create a dramatic title card frame.

    Style: Dark background, large centered title, subtle red accent line,
    smaller subtitle below.
    """
    # Create base image
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Load fonts
    title_font = ImageFont.truetype(find_font("title"), title_size)
    subtitle_font = ImageFont.truetype(find_font("subtitle"), subtitle_size)

    # Calculate title position (centered, slightly above middle)
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_height = title_bbox[3] - title_bbox[1]
    title_x = (width - title_width) // 2
    title_y = (height - title_height) // 2 - 60

    # Draw title with slight shadow for depth
    shadow_offset = 3
    draw.text((title_x + shadow_offset, title_y + shadow_offset),
              title, fill=(0, 0, 0), font=title_font)
    draw.text((title_x, title_y), title, fill=title_color, font=title_font)

    # Draw accent line below title
    line_y = title_y + title_height + 30
    line_width = min(title_width + 100, width - 200)
    line_x_start = (width - line_width) // 2
    draw.rectangle(
        [(line_x_start, line_y), (line_x_start + line_width, line_y + 4)],
        fill=accent_color
    )

    # Draw subtitle if provided
    if subtitle:
        sub_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        sub_width = sub_bbox[2] - sub_bbox[0]
        sub_x = (width - sub_width) // 2
        sub_y = line_y + 40
        draw.text((sub_x, sub_y), subtitle, fill=(180, 180, 180), font=subtitle_font)

    return img


def create_title_video(
    title: str,
    subtitle: str = None,
    output_path: str = None,
    duration: float = 6.0,
    width: int = 1920,
    height: int = 1080,
    fade_duration: float = 0.5,
) -> str:
    """
    Create a title card video with fade effects.
    """
    print(f"Creating title card: \"{title}\"")
    if subtitle:
        print(f"Subtitle: \"{subtitle}\"")

    # Create the title frame
    frame = create_title_frame(
        title=title,
        subtitle=subtitle,
        width=width,
        height=height,
    )

    # Convert to numpy array
    frame_array = np.array(frame)

    # Create video clip
    clip = ImageClip(frame_array, duration=duration)

    # Add fade effects (moviepy 2.x syntax)
    clip = clip.with_start(0)  # Ensure clip starts at 0

    # Write video
    if output_path is None:
        output_path = "title_card.mp4"

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
    title: str,
    subtitle: str = None,
    output_path: str = None,
    duration: float = 6.0,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """
    Render title card with Quality Protocol validation.
    """
    print("\n" + "="*60)
    print("NOLAN Quality Protocol - Title Card Render")
    print("="*60 + "\n")

    # Configure QA
    config = QAConfig(
        check_properties=True,
        check_visual=True,
        check_text=False,
        duration_tolerance=0.5,
    )
    qa = QualityProtocol(config)

    # Render
    print("[QA] Rendering title card with PIL...")
    result_path = create_title_video(
        title=title,
        subtitle=subtitle,
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
        print(f"\n[QA] SUCCESS - Title card passed all quality checks!")
    else:
        print(f"\n[QA] WARNING - Some checks failed (see above)")

    print(f"[QA] Output: {result_path}")
    return result_path


def main():
    """Render the Venezuela documentary title card."""
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    output_path = str(output_dir / "venezuela_title_card.mp4")

    # Hook scene_008: Main documentary title
    render_with_quality_check(
        title="VENEZUELA: THE PRICE OF OIL",
        subtitle="How a nation with incredible wealth became so fractured",
        output_path=output_path,
        duration=6.0,
    )


if __name__ == "__main__":
    main()
