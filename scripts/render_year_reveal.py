#!/usr/bin/env python3
"""
Year/Date reveal renderer with Quality Protocol.
Creates dramatic year overlays for historical documentary moments.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip
from nolan.quality import QualityProtocol, QAConfig


def find_font(bold: bool = True) -> str:
    """Find available font."""
    fonts = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for f in fonts:
        if Path(f).exists():
            return f
    return fonts[0]


def create_year_frame(
    year: str,
    label: str = None,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple = (20, 18, 15),        # Sepia-ish dark
    year_color: str = "white",
    label_color: tuple = (200, 180, 140),  # Gold/sepia tint
    accent_color: tuple = (180, 140, 80),  # Gold accent
    year_size: int = 200,
    label_size: int = 48,
) -> Image.Image:
    """
    Create a dramatic year reveal frame.

    Style: Large centered year number, optional label below,
    subtle gold accent styling for historical feel.
    """
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Load fonts - use Impact or bold for dramatic effect
    year_font = ImageFont.truetype(find_font(bold=True), year_size)
    label_font = ImageFont.truetype(find_font(bold=False), label_size)

    # Calculate year position (centered)
    year_bbox = draw.textbbox((0, 0), year, font=year_font)
    year_width = year_bbox[2] - year_bbox[0]
    year_height = year_bbox[3] - year_bbox[1]
    year_x = (width - year_width) // 2
    year_y = (height - year_height) // 2 - (40 if label else 0)

    # Draw subtle shadow
    shadow_offset = 4
    draw.text((year_x + shadow_offset, year_y + shadow_offset),
              year, fill=(0, 0, 0), font=year_font)

    # Draw year
    draw.text((year_x, year_y), year, fill=year_color, font=year_font)

    # Draw decorative lines on sides
    line_y = year_y + year_height // 2
    line_length = 150
    line_gap = 50

    # Left line
    left_line_end = year_x - line_gap
    left_line_start = left_line_end - line_length
    if left_line_start > 50:
        draw.rectangle(
            [(left_line_start, line_y - 2), (left_line_end, line_y + 2)],
            fill=accent_color
        )

    # Right line
    right_line_start = year_x + year_width + line_gap
    right_line_end = right_line_start + line_length
    if right_line_end < width - 50:
        draw.rectangle(
            [(right_line_start, line_y - 2), (right_line_end, line_y + 2)],
            fill=accent_color
        )

    # Draw label if provided
    if label:
        label_bbox = draw.textbbox((0, 0), label, font=label_font)
        label_width = label_bbox[2] - label_bbox[0]
        label_x = (width - label_width) // 2
        label_y = year_y + year_height + 30
        draw.text((label_x, label_y), label, fill=label_color, font=label_font)

    return img


def create_year_video(
    year: str,
    label: str = None,
    output_path: str = None,
    duration: float = 5.0,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Create a year reveal video."""
    print(f"Creating year reveal: \"{year}\"")
    if label:
        print(f"Label: \"{label}\"")

    frame = create_year_frame(
        year=year,
        label=label,
        width=width,
        height=height,
    )

    frame_array = np.array(frame)
    clip = ImageClip(frame_array, duration=duration)

    if output_path is None:
        output_path = "year_reveal.mp4"

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
    year: str,
    label: str = None,
    output_path: str = None,
    duration: float = 5.0,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Render year reveal with Quality Protocol validation."""
    print("\n" + "="*60)
    print("NOLAN Quality Protocol - Year Reveal Render")
    print("="*60 + "\n")

    config = QAConfig(
        check_properties=True,
        check_visual=True,
        check_text=False,
        duration_tolerance=0.5,
    )
    qa = QualityProtocol(config)

    print("[QA] Rendering year reveal with PIL...")
    result_path = create_year_video(
        year=year,
        label=label,
        output_path=output_path,
        duration=duration,
        width=width,
        height=height,
    )

    print("\n[QA] Running validation checks...")
    qa_result = qa.validate(
        video_path=result_path,
        expected_duration=duration,
        expected_resolution=(width, height),
    )

    print(f"\n{qa_result.summary()}")

    if qa_result.passed:
        print(f"\n[QA] SUCCESS - Year reveal passed all quality checks!")
    else:
        print(f"\n[QA] WARNING - Some checks failed")

    print(f"[QA] Output: {result_path}")
    return result_path


def main():
    """Render the Venezuela independence year reveal."""
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    output_path = str(output_dir / "venezuela_1821_independence.mp4")

    # Context scene_005: Independence year
    render_with_quality_check(
        year="1821",
        label="INDEPENDENCIA",
        output_path=output_path,
        duration=5.0,
    )


if __name__ == "__main__":
    main()
