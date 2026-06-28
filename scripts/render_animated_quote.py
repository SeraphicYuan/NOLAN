#!/usr/bin/env python3
"""
Animated quote video renderer with fade and reveal effects.
Uses PIL for frames + moviepy for animation sequencing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips, VideoClip
from nolan.quality import QualityProtocol, QAConfig


def find_font(bold: bool = True) -> str:
    fonts = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for f in fonts:
        if Path(f).exists():
            return f
    return fonts[0]


def create_text_frame(
    text: str,
    width: int,
    height: int,
    font_size: int,
    color: tuple,
    bg_color: tuple,
    y_offset: int = 0,
    font_bold: bool = True,
) -> np.ndarray:
    """Create a single text frame."""
    img = Image.new('RGBA', (width, height), (*bg_color, 255))
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype(find_font(font_bold), font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (width - text_width) // 2
    y = (height - text_height) // 2 + y_offset

    draw.text((x, y), text, fill=color, font=font)

    return np.array(img.convert('RGB'))


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out function for smooth deceleration."""
    return 1 - pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out for smooth acceleration and deceleration."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def create_animated_quote(
    quote: str,
    attribution: str,
    output_path: str,
    duration: float = 7.0,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple = (26, 26, 26),
    text_color: tuple = (255, 255, 255),
    attr_color: tuple = (136, 136, 136),
    accent_color: tuple = (220, 38, 38),
) -> str:
    """
    Create an animated quote video with:
    - Fade in from black
    - Quote text slides up and fades in
    - Attribution fades in after quote
    - Accent bar animates in
    - Fade out to black
    """
    print(f"Creating animated quote: \"{quote}\"")

    fps = 30

    # Timing (in seconds)
    fade_in_start = 0.0
    fade_in_end = 0.8
    quote_reveal_start = 0.3
    quote_reveal_end = 1.5
    attr_reveal_start = 1.2
    attr_reveal_end = 2.0
    bar_reveal_start = 1.0
    bar_reveal_end = 1.8
    hold_until = duration - 1.0
    fade_out_start = duration - 1.0
    fade_out_end = duration

    total_frames = int(duration * fps)
    frames = []

    # Pre-calculate text positions
    font_quote = ImageFont.truetype(find_font(True), 72)
    font_attr = ImageFont.truetype(find_font(False), 36)

    # Create base image for measurements
    temp_img = Image.new('RGB', (width, height))
    temp_draw = ImageDraw.Draw(temp_img)

    quote_bbox = temp_draw.textbbox((0, 0), quote, font=font_quote)
    quote_w = quote_bbox[2] - quote_bbox[0]
    quote_h = quote_bbox[3] - quote_bbox[1]
    quote_x = (width - quote_w) // 2
    quote_y_final = (height - quote_h) // 2 - 40

    attr_bbox = temp_draw.textbbox((0, 0), attribution, font=font_attr)
    attr_w = attr_bbox[2] - attr_bbox[0]
    attr_x = (width - attr_w) // 2
    attr_y = int(height * 0.62)

    bar_y = height - 108
    bar_width = width

    print(f"Generating {total_frames} frames...")

    for frame_idx in range(total_frames):
        t = frame_idx / fps  # Current time in seconds

        # Create frame
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Calculate animation states

        # 1. Global fade (black overlay)
        if t < fade_in_end:
            fade_progress = (t - fade_in_start) / (fade_in_end - fade_in_start)
            fade_progress = max(0, min(1, fade_progress))
            global_alpha = ease_out_cubic(fade_progress)
        elif t > fade_out_start:
            fade_progress = (t - fade_out_start) / (fade_out_end - fade_out_start)
            fade_progress = max(0, min(1, fade_progress))
            global_alpha = 1 - ease_in_out_cubic(fade_progress)
        else:
            global_alpha = 1.0

        # 2. Quote reveal (slide up + fade)
        if t < quote_reveal_start:
            quote_alpha = 0
            quote_y_offset = 50
        elif t < quote_reveal_end:
            progress = (t - quote_reveal_start) / (quote_reveal_end - quote_reveal_start)
            progress = ease_out_cubic(progress)
            quote_alpha = progress
            quote_y_offset = 50 * (1 - progress)
        else:
            quote_alpha = 1
            quote_y_offset = 0

        # 3. Attribution reveal (fade only)
        if t < attr_reveal_start:
            attr_alpha = 0
        elif t < attr_reveal_end:
            progress = (t - attr_reveal_start) / (attr_reveal_end - attr_reveal_start)
            attr_alpha = ease_out_cubic(progress)
        else:
            attr_alpha = 1

        # 4. Accent bar reveal (width animation)
        if t < bar_reveal_start:
            bar_progress = 0
        elif t < bar_reveal_end:
            progress = (t - bar_reveal_start) / (bar_reveal_end - bar_reveal_start)
            bar_progress = ease_out_cubic(progress)
        else:
            bar_progress = 1

        # Draw elements

        # Accent bar (animates from center outward)
        if bar_progress > 0:
            current_bar_width = int(bar_width * bar_progress)
            bar_x_start = (width - current_bar_width) // 2
            draw.rectangle(
                [(bar_x_start, bar_y), (bar_x_start + current_bar_width, bar_y + 8)],
                fill=accent_color
            )

        # Quote text
        if quote_alpha > 0:
            quote_color_with_alpha = tuple(int(c * quote_alpha) for c in text_color)
            # Blend with background for fade effect
            blended_quote_color = tuple(
                int(bg_color[i] + (text_color[i] - bg_color[i]) * quote_alpha)
                for i in range(3)
            )
            draw.text(
                (quote_x, quote_y_final + int(quote_y_offset)),
                quote,
                fill=blended_quote_color,
                font=font_quote
            )

        # Attribution
        if attr_alpha > 0:
            blended_attr_color = tuple(
                int(bg_color[i] + (attr_color[i] - bg_color[i]) * attr_alpha)
                for i in range(3)
            )
            draw.text((attr_x, attr_y), attribution, fill=blended_attr_color, font=font_attr)

        # Apply global fade (darken entire frame)
        if global_alpha < 1:
            # Blend frame with black
            frame_array = np.array(img)
            frame_array = (frame_array * global_alpha).astype(np.uint8)
            img = Image.fromarray(frame_array)

        frames.append(np.array(img))

    print("Encoding video...")

    # Create video from frames using VideoClip
    def make_frame(t):
        frame_idx = min(int(t * fps), len(frames) - 1)
        return frames[frame_idx]

    clip = VideoClip(make_frame, duration=duration)

    clip.write_videofile(
        output_path,
        fps=fps,
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
) -> str:
    """Render animated quote with Quality Protocol validation."""
    print("\n" + "="*60)
    print("NOLAN Quality Protocol - Animated Quote Render")
    print("="*60 + "\n")

    config = QAConfig(
        check_properties=True,
        check_visual=True,
        check_text=False,
        duration_tolerance=0.5,
    )
    qa = QualityProtocol(config)

    print("[QA] Rendering animated quote...")
    result_path = create_animated_quote(
        quote=quote,
        attribution=attribution,
        output_path=output_path,
        duration=duration,
    )

    print("\n[QA] Running validation checks...")
    qa_result = qa.validate(
        video_path=result_path,
        expected_duration=duration,
        expected_resolution=(1920, 1080),
    )

    print(f"\n{qa_result.summary()}")

    if qa_result.passed:
        print(f"\n[QA] SUCCESS - Animated quote passed all quality checks!")
    else:
        print(f"\n[QA] WARNING - Some checks failed")

    print(f"[QA] Output: {result_path}")
    return result_path


def main():
    output_dir = Path(__file__).parent.parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    output_path = str(output_dir / "venezuela_quote_animated.mp4")

    render_with_quality_check(
        quote="WE ARE TIRED",
        attribution="— Maria Rodriguez, Caracas Resident",
        output_path=output_path,
        duration=7.0,
    )


if __name__ == "__main__":
    main()
