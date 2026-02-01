"""
Test script for text annotation and cinematic effects.

Tests:
1. Underline - Highlighter-style text emphasis
2. Strikethrough - Cross out text
3. Circle annotation - Draw attention
4. Arrow pointing - Direct attention
5. Letterbox - Cinematic bars
6. Scanlines - Retro CRT effect
7. ColorTint - Mood color overlay
8. DrawLine - Connecting ideas
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.base import BaseRenderer, Element
from src.nolan.renderer.effects import (
    FadeIn, SlideUp, ScaleIn,
    # Annotation effects
    Underline, Strikethrough, CircleAnnotation, ArrowPoint,
    # Cinematic effects
    Letterbox, Scanlines, ColorTint, VHSEffect,
    # Drawing effects
    DrawLine, DrawBox,
    # Sequencing
    Sequence, Loop, Delay,
)

OUTPUT_DIR = "test_output/annotation_effects"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_underline():
    """Test underline/highlighter effect."""
    print("\n[1/8] Testing Underline effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Main text with underline
    text = Element(
        id="text",
        element_type="text",
        text="The key finding was remarkable",
        font_size=56,
        color=(255, 255, 255),
        x='center',
        y=450,
    )
    text.add_effects([
        FadeIn(start=0.2, duration=0.5),
        Underline(
            start=0.8, duration=1.0,
            color=(255, 220, 100),
            thickness=8,
            offset_y=8,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(text)

    # Subtitle
    sub = Element(
        id="sub",
        element_type="text",
        text="Highlighting important information",
        font_size=28,
        color=(150, 150, 160),
        x='center',
        y=550,
    )
    sub.add_effect(FadeIn(start=1.5, duration=0.5))
    renderer.add_element(sub)

    output = f"{OUTPUT_DIR}/01_underline.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_strikethrough():
    """Test strikethrough effect."""
    print("\n[2/8] Testing Strikethrough effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Original claim
    old_text = Element(
        id="old",
        element_type="text",
        text="The economy is doing great",
        font_size=48,
        color=(180, 180, 190),
        x='center',
        y=400,
    )
    old_text.add_effects([
        FadeIn(start=0.2, duration=0.5),
        Strikethrough(
            start=1.0, duration=0.8,
            color=(255, 80, 80),
            thickness=4,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(old_text)

    # Correction
    new_text = Element(
        id="new",
        element_type="text",
        text="GDP fell by 88%",
        font_size=56,
        color=(255, 100, 100),
        x='center',
        y=520,
    )
    new_text.add_effects([
        FadeIn(start=1.8, duration=0.5),
        ScaleIn(start=1.8, duration=0.5, from_scale=0.9, easing="ease_out_back"),
    ])
    renderer.add_element(new_text)

    output = f"{OUTPUT_DIR}/02_strikethrough.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_circle_annotation():
    """Test circle annotation effect."""
    print("\n[3/8] Testing Circle Annotation effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Key term to highlight
    key_text = Element(
        id="key",
        element_type="text",
        text="HYPERINFLATION",
        font_size=72,
        color=(255, 200, 100),
        x='center',
        y=450,
    )
    key_text.add_effects([
        FadeIn(start=0.2, duration=0.5),
        CircleAnnotation(
            start=0.8, duration=1.2,
            color=(255, 100, 100),
            thickness=4,
            padding=25,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(key_text)

    # Context
    context = Element(
        id="context",
        element_type="text",
        text="The root cause of the crisis",
        font_size=28,
        color=(150, 150, 160),
        x='center',
        y=580,
    )
    context.add_effect(FadeIn(start=1.5, duration=0.5))
    renderer.add_element(context)

    output = f"{OUTPUT_DIR}/03_circle.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_arrow():
    """Test arrow pointing effect."""
    print("\n[4/8] Testing Arrow Point effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Target element
    target = Element(
        id="target",
        element_type="text",
        text="Key Data Point",
        font_size=48,
        color=(255, 255, 255),
        x='center',
        y=450,
    )
    target.add_effects([
        FadeIn(start=0.2, duration=0.5),
        ArrowPoint(
            start=0.8, duration=1.0,
            color=(255, 200, 100),
            direction="left",
            size=40,
            offset=80,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(target)

    output = f"{OUTPUT_DIR}/04_arrow.mp4"
    renderer.render(output, duration=3.5)
    print(f"  [OK] Saved to {output}")


def test_letterbox():
    """Test letterbox cinematic effect."""
    print("\n[5/8] Testing Letterbox effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(30, 30, 40))

    # Frame effects element for letterbox
    frame_fx = Element(
        id="_frame_effects",
        element_type="text",
        text="",
        visible=False,
    )
    frame_fx.add_effects([
        Letterbox(
            start=0.3, duration=1.0,
            bar_height=0.12,
            color=(0, 0, 0),
            mode="in",
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(frame_fx)

    # Dramatic text
    title = Element(
        id="title",
        element_type="text",
        text="THE COLLAPSE",
        font_size=96,
        color=(255, 255, 255),
        x='center',
        y=480,
    )
    title.add_effects([
        FadeIn(start=0.8, duration=0.8),
        ScaleIn(start=0.8, duration=0.8, from_scale=0.95, easing="ease_out_cubic"),
    ])
    renderer.add_element(title)

    # Subtitle
    sub = Element(
        id="sub",
        element_type="text",
        text="A Documentary",
        font_size=32,
        color=(180, 180, 190),
        x='center',
        y=600,
    )
    sub.add_effect(FadeIn(start=1.5, duration=0.5))
    renderer.add_element(sub)

    output = f"{OUTPUT_DIR}/05_letterbox.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_scanlines():
    """Test scanlines retro effect."""
    print("\n[6/8] Testing Scanlines effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(15, 15, 20))

    # Frame effects for scanlines
    frame_fx = Element(
        id="_frame_effects",
        element_type="text",
        text="",
        visible=False,
    )
    frame_fx.add_effects([
        Scanlines(
            start=0.2, duration=3.5,
            line_spacing=3,
            opacity=0.25,
            moving=True,
            speed=30,
            easing="linear"
        ),
    ])
    renderer.add_element(frame_fx)

    # Retro text
    text = Element(
        id="text",
        element_type="text",
        text="ARCHIVE FOOTAGE",
        font_size=64,
        color=(200, 200, 180),
        x='center',
        y=450,
    )
    text.add_effect(FadeIn(start=0.3, duration=0.5))
    renderer.add_element(text)

    # Date
    date = Element(
        id="date",
        element_type="text",
        text="CARACAS, 1999",
        font_size=32,
        color=(150, 150, 140),
        x='center',
        y=550,
    )
    date.add_effect(FadeIn(start=0.8, duration=0.5))
    renderer.add_element(date)

    output = f"{OUTPUT_DIR}/06_scanlines.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_color_tint():
    """Test color tint mood effect."""
    print("\n[7/8] Testing ColorTint effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(40, 35, 30))

    # Main text
    text = Element(
        id="text",
        element_type="text",
        text="THE GOLDEN ERA",
        font_size=72,
        color=(255, 255, 255),
        x='center',
        y=450,
    )
    text.add_effects([
        FadeIn(start=0.2, duration=0.5),
        ColorTint(
            start=0.5, duration=2.0,
            color=(255, 200, 120),  # Warm sepia
            intensity=0.25,
            mode="in",
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(text)

    # Subtitle
    sub = Element(
        id="sub",
        element_type="text",
        text="Before the crisis",
        font_size=32,
        color=(180, 170, 160),
        x='center',
        y=560,
    )
    sub.add_effect(FadeIn(start=1.0, duration=0.5))
    renderer.add_element(sub)

    output = f"{OUTPUT_DIR}/07_color_tint.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_draw_line():
    """Test draw line effect."""
    print("\n[8/8] Testing DrawLine effect...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Point A
    point_a = Element(
        id="point_a",
        element_type="text",
        text="CAUSE",
        font_size=48,
        color=(100, 200, 150),
        x=400,
        y=400,
    )
    point_a.add_effect(FadeIn(start=0.2, duration=0.5))
    renderer.add_element(point_a)

    # Point B
    point_b = Element(
        id="point_b",
        element_type="text",
        text="EFFECT",
        font_size=48,
        color=(255, 150, 100),
        x=1400,
        y=600,
    )
    point_b.add_effect(FadeIn(start=0.5, duration=0.5))
    renderer.add_element(point_b)

    # Connecting line (rendered separately as we need custom positioning)
    line = Element(
        id="line",
        element_type="text",
        text="",  # Just for the effect
        x=500,
        y=430,
    )
    line.add_effect(
        DrawLine(
            start=1.0, duration=1.5,
            start_point=(550, 420),
            end_point=(1350, 600),
            color=(200, 200, 200),
            thickness=3,
            easing="ease_out_cubic"
        )
    )
    renderer.add_element(line)

    output = f"{OUTPUT_DIR}/08_draw_line.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def main():
    print("=" * 70)
    print("TESTING ANNOTATION & CINEMATIC EFFECTS")
    print("=" * 70)

    test_underline()
    test_strikethrough()
    test_circle_annotation()
    test_arrow()
    test_letterbox()
    test_scanlines()
    test_color_tint()
    test_draw_line()

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED!")
    print("=" * 70)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print("\nGenerated videos:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.mp4'):
            print(f"  - {f}")

    print("\n" + "=" * 70)
    print("Annotation & Cinematic Effects Summary:")
    print("  Text Annotations:")
    print("    - Underline:    Highlighter-style emphasis")
    print("    - Strikethrough: Cross out incorrect text")
    print("    - Circle:       Draw attention to key terms")
    print("    - Arrow:        Point to important elements")
    print("  Cinematic:")
    print("    - Letterbox:    Cinematic black bars")
    print("    - Scanlines:    Retro CRT/VHS effect")
    print("    - ColorTint:    Mood color overlay")
    print("  Drawing:")
    print("    - DrawLine:     Connect ideas visually")
    print("=" * 70)


if __name__ == "__main__":
    main()
