"""
Portrait Reveal Scene Template

Shows a portrait/image area that slides to one side, revealing a text box
with title and animated bullet points on the other side.

Great for:
- Introducing historical figures
- Quoting experts/thinkers
- Presenting key concepts from a person

Animation sequence:
1. Portrait area appears centered
2. Portrait area slides to left/right
3. Text box fades in on opposite side
4. Title appears
5. Bullet points reveal one by one

Layout System Integration:
This template uses the NOLAN Layout system for positioning.
It can accept a custom layout or use the default "portrait-reveal" preset.
"""

from typing import List, Optional, Tuple, Literal, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, MoveTo
from ..layout import Layout, Slot, get_preset


def render_portrait_reveal(
    # Content
    title: str,
    points: List[str],
    # Optional image (placeholder rectangle if not provided)
    image_path: Optional[str] = None,
    portrait_caption: Optional[str] = None,
    # Layout - can pass custom slots or use defaults
    layout: Optional[List[Slot]] = None,
    portrait_side: Literal["left", "right"] = "left",
    # Timing
    portrait_hold: float = 1.5,      # How long portrait stays centered
    slide_duration: float = 0.8,     # Portrait slide animation
    title_delay: float = 0.3,        # Delay after slide before title
    point_interval: float = 0.6,     # Time between each point
    point_fade_duration: float = 0.4,
    # Sizing
    width: int = 1920,
    height: int = 1080,
    portrait_width: int = 350,
    portrait_height: int = 450,
    # Colors
    bg_color: Tuple[int, int, int] = (10, 10, 18),
    border_color: Tuple[int, int, int] = (180, 150, 80),
    portrait_bg_color: Tuple[int, int, int] = (40, 40, 50),
    title_color: Tuple[int, int, int] = (200, 170, 100),
    title_size: int = 56,
    point_color: Tuple[int, int, int] = (220, 220, 230),
    point_size: int = 32,
    caption_color: Tuple[int, int, int] = (150, 150, 160),
    caption_size: int = 24,
    # Output
    output_path: Optional[str] = None,
    fps: int = 30,
) -> str:
    """
    Render a portrait reveal animation.

    Args:
        title: Main title text (appears above points)
        points: List of bullet points to reveal
        image_path: Path to portrait image (uses placeholder if None)
        portrait_caption: Optional caption under portrait
        layout: Optional list of 2 Slots [portrait_slot, content_slot].
                If None, uses default "portrait-reveal" layout.
        portrait_side: Which side portrait ends up ("left" or "right")
        portrait_hold: Seconds portrait stays centered before sliding
        slide_duration: Duration of slide animation
        title_delay: Delay after slide before title appears
        point_interval: Time between each point appearing
        point_fade_duration: Fade duration for each point
        width, height: Video dimensions
        portrait_width, portrait_height: Portrait dimensions
        bg_color: Background color
        border_color: Portrait border color (gold)
        portrait_bg_color: Portrait area fill color
        title_color: Title text color
        title_size: Title font size
        point_color: Bullet point text color
        point_size: Bullet point font size
        caption_color: Portrait caption color
        caption_size: Caption font size
        output_path: Output file path
        fps: Frames per second

    Returns:
        Path to rendered video
    """
    renderer = BaseRenderer(width=width, height=height, fps=fps, bg_color=bg_color)

    # === LAYOUT SETUP ===
    # Use provided layout or create default
    if layout is None:
        # Create layout with 1:2 ratio for portrait:content
        layout_obj = Layout(width=width, height=height, margin=100, default_gap=60)
        if portrait_side == "left":
            layout = layout_obj.columns([1, 2], names=["portrait", "content"])
        else:
            layout = layout_obj.columns([2, 1], names=["content", "portrait"])

    # Get slots based on portrait side
    if portrait_side == "left":
        portrait_slot, content_slot = layout[0], layout[1]
    else:
        content_slot, portrait_slot = layout[0], layout[1]

    # === CALCULATE POSITIONS FROM SLOTS ===
    center_x = width // 2
    center_y = height // 2

    # Portrait starts centered, ends in its slot
    portrait_start_x = center_x - portrait_width // 2
    portrait_end_x = portrait_slot.align_x(portrait_width, "center")
    portrait_y = portrait_slot.align_y(portrait_height, "center") - 30  # Slight offset for caption

    # Calculate slide distance
    slide_distance_x = portrait_end_x - portrait_start_x

    # Text box uses content slot
    text_box_x = content_slot.x
    text_box_y = portrait_y  # Align with portrait top
    text_box_width = content_slot.width
    text_box_padding = content_slot.padding

    # Text area (inside the text box)
    text_x = content_slot.inner_x
    text_width = content_slot.inner_width

    # === TIMELINE ===
    t_portrait_appear = 0.2
    t_slide_start = t_portrait_appear + portrait_hold
    t_slide_end = t_slide_start + slide_duration
    t_textbox_start = t_slide_end + 0.1  # Text box appears slightly after slide
    t_title_start = t_textbox_start + title_delay
    t_points_start = t_title_start + 0.6

    # Calculate total duration
    total_duration = t_points_start + len(points) * point_interval + 2.0

    # Calculate text box height based on content
    point_spacing = point_size + 25
    content_height = text_box_padding + title_size + 50 + len(points) * point_spacing + text_box_padding
    text_box_height = max(content_height, portrait_height)  # At least as tall as portrait

    # === PORTRAIT AREA (placeholder rectangle) ===
    portrait_bg = Element(
        id="portrait_bg",
        element_type="rectangle",
        x=portrait_start_x,
        y=portrait_y,
        width=portrait_width,
        height=portrait_height,
        color=portrait_bg_color,
    )
    portrait_bg.add_effects([
        FadeIn(start=t_portrait_appear, duration=0.5),
        MoveTo(
            start=t_slide_start,
            duration=slide_duration,
            delta_x=slide_distance_x,
            delta_y=0,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(portrait_bg)

    # === PORTRAIT BORDER (4 lines to create frame) ===
    border_thickness = 3

    # Top border
    border_top = Element(
        id="border_top",
        element_type="rectangle",
        x=portrait_start_x - border_thickness,
        y=portrait_y - border_thickness,
        width=portrait_width + border_thickness * 2,
        height=border_thickness,
        color=border_color,
    )
    border_top.add_effects([
        FadeIn(start=t_portrait_appear, duration=0.5),
        MoveTo(start=t_slide_start, duration=slide_duration, delta_x=slide_distance_x, easing="ease_out_cubic"),
    ])
    renderer.add_element(border_top)

    # Bottom border
    border_bottom = Element(
        id="border_bottom",
        element_type="rectangle",
        x=portrait_start_x - border_thickness,
        y=portrait_y + portrait_height,
        width=portrait_width + border_thickness * 2,
        height=border_thickness,
        color=border_color,
    )
    border_bottom.add_effects([
        FadeIn(start=t_portrait_appear, duration=0.5),
        MoveTo(start=t_slide_start, duration=slide_duration, delta_x=slide_distance_x, easing="ease_out_cubic"),
    ])
    renderer.add_element(border_bottom)

    # Left border
    border_left = Element(
        id="border_left",
        element_type="rectangle",
        x=portrait_start_x - border_thickness,
        y=portrait_y,
        width=border_thickness,
        height=portrait_height,
        color=border_color,
    )
    border_left.add_effects([
        FadeIn(start=t_portrait_appear, duration=0.5),
        MoveTo(start=t_slide_start, duration=slide_duration, delta_x=slide_distance_x, easing="ease_out_cubic"),
    ])
    renderer.add_element(border_left)

    # Right border
    border_right = Element(
        id="border_right",
        element_type="rectangle",
        x=portrait_start_x + portrait_width,
        y=portrait_y,
        width=border_thickness,
        height=portrait_height,
        color=border_color,
    )
    border_right.add_effects([
        FadeIn(start=t_portrait_appear, duration=0.5),
        MoveTo(start=t_slide_start, duration=slide_duration, delta_x=slide_distance_x, easing="ease_out_cubic"),
    ])
    renderer.add_element(border_right)

    # === PORTRAIT CAPTION (optional) ===
    if portrait_caption:
        # x is the LEFT edge of the text block; text_align="center" centers within max_width
        caption = Element(
            id="portrait_caption",
            element_type="text",
            text=portrait_caption,
            font_size=caption_size,
            color=caption_color,
            x=portrait_start_x,  # Left edge of portrait (text centers within max_width)
            y=portrait_y + portrait_height + 30,
            text_align="center",
            max_width=portrait_width,
        )
        caption.add_effects([
            FadeIn(start=t_portrait_appear + 0.3, duration=0.4),
            MoveTo(start=t_slide_start, duration=slide_duration, delta_x=slide_distance_x, easing="ease_out_cubic"),
        ])
        renderer.add_element(caption)

    # === TEXT BOX BORDER ===
    textbox_border_thickness = 2

    # Text box background (slightly darker than main bg for contrast)
    text_box_bg = Element(
        id="text_box_bg",
        element_type="rectangle",
        x=text_box_x,
        y=text_box_y,
        width=text_box_width,
        height=text_box_height,
        color=(bg_color[0] + 8, bg_color[1] + 8, bg_color[2] + 12),  # Slightly lighter
    )
    text_box_bg.add_effect(FadeIn(start=t_textbox_start, duration=0.4))
    renderer.add_element(text_box_bg)

    # Text box border - top
    textbox_border_top = Element(
        id="textbox_border_top",
        element_type="rectangle",
        x=text_box_x,
        y=text_box_y,
        width=text_box_width,
        height=textbox_border_thickness,
        color=border_color,
    )
    textbox_border_top.add_effect(FadeIn(start=t_textbox_start, duration=0.4))
    renderer.add_element(textbox_border_top)

    # Text box border - bottom
    textbox_border_bottom = Element(
        id="textbox_border_bottom",
        element_type="rectangle",
        x=text_box_x,
        y=text_box_y + text_box_height - textbox_border_thickness,
        width=text_box_width,
        height=textbox_border_thickness,
        color=border_color,
    )
    textbox_border_bottom.add_effect(FadeIn(start=t_textbox_start, duration=0.4))
    renderer.add_element(textbox_border_bottom)

    # Text box border - left
    textbox_border_left = Element(
        id="textbox_border_left",
        element_type="rectangle",
        x=text_box_x,
        y=text_box_y,
        width=textbox_border_thickness,
        height=text_box_height,
        color=border_color,
    )
    textbox_border_left.add_effect(FadeIn(start=t_textbox_start, duration=0.4))
    renderer.add_element(textbox_border_left)

    # Text box border - right
    textbox_border_right = Element(
        id="textbox_border_right",
        element_type="rectangle",
        x=text_box_x + text_box_width - textbox_border_thickness,
        y=text_box_y,
        width=textbox_border_thickness,
        height=text_box_height,
        color=border_color,
    )
    textbox_border_right.add_effect(FadeIn(start=t_textbox_start, duration=0.4))
    renderer.add_element(textbox_border_right)

    # === TITLE ===
    title_y = text_box_y + text_box_padding
    title_elem = Element(
        id="title",
        element_type="text",
        text=title,
        font_size=title_size,
        color=title_color,
        x=text_x,
        y=title_y,
        text_align="left",
        max_width=text_width,
    )
    title_elem.add_effect(FadeIn(start=t_title_start, duration=0.5))
    renderer.add_element(title_elem)

    # === BULLET POINTS ===
    point_y = title_y + title_size + 40

    for i, point_text in enumerate(points):
        t_point = t_points_start + i * point_interval

        point = Element(
            id=f"point_{i}",
            element_type="text",
            text=point_text,
            font_size=point_size,
            color=point_color,
            x=text_x,
            y=point_y + i * point_spacing,
            text_align="left",
            max_width=text_width,
        )
        point.add_effect(FadeIn(start=t_point, duration=point_fade_duration))
        renderer.add_element(point)

    # Render
    if output_path is None:
        output_path = "portrait_reveal.mp4"

    renderer.render(output_path, duration=total_duration)
    return output_path


# Convenience function
def portrait_reveal(title: str, points: List[str], output_path: str = "portrait_reveal.mp4", **kwargs) -> str:
    """Quick portrait reveal render."""
    return render_portrait_reveal(title=title, points=points, output_path=output_path, **kwargs)
