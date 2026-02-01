"""
Test script for all new effects using Venezuela documentary content.

Tests:
1. CountUp - Economic statistics animation
2. Shake - Warning emphasis
3. Rotation effects - Spinning icons, rotating text
4. Blur effects - Focus transitions
5. Shadow and Glow - Emphasis effects
6. New easing functions - Bounce, elastic, spring
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.base import BaseRenderer, Element
from src.nolan.renderer.effects import (
    FadeIn, FadeOut, SlideUp, ScaleIn,
    # New effects
    CountUp, Shake, Flash, Bounce, Glitch, Reveal, Hold,
    RotateIn, RotateOut, Spin, Wobble,
    BlurIn, BlurOut, FocusPull, PulseBlur,
    ShadowIn, ShadowOut, ShadowPulse,
    GlowIn, GlowOut, GlowPulse, Highlight,
    EffectPresets,
)

OUTPUT_DIR = "test_output/new_effects"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_count_up():
    """Test CountUp effect with Venezuela GDP collapse."""
    print("\n[1/10] Testing CountUp effect - GDP Collapse...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Title
    title = Element(
        id="title",
        element_type="text",
        text="VENEZUELA GDP COLLAPSE",
        font_size=36,
        color=(150, 150, 160),
        x='center',
        y=300,
    )
    title.add_effect(FadeIn(start=0.2, duration=0.5))
    renderer.add_element(title)

    # GDP number with CountUp
    gdp = Element(
        id="gdp",
        element_type="text",
        text="$100,000,000,000",  # Will be replaced by CountUp
        font_size=96,
        color=(255, 100, 100),
        x='center',
        y=450,
    )
    gdp.add_effects([
        FadeIn(start=0.5, duration=0.3),
        ScaleIn(start=0.5, duration=0.5, from_scale=0.8, easing="ease_out_back"),
        CountUp(
            start=0.8, duration=3.0,
            from_value=100, to_value=12,
            prefix="$", suffix=" Billion",
            decimals=0, use_commas=True,
            easing="ease_out_cubic"
        ),
    ])
    renderer.add_element(gdp)

    # Subtitle
    subtitle = Element(
        id="subtitle",
        element_type="text",
        text="2012 to 2020",
        font_size=28,
        color=(120, 120, 140),
        x='center',
        y=580,
    )
    subtitle.add_effect(FadeIn(start=1.0, duration=0.5))
    renderer.add_element(subtitle)

    output = f"{OUTPUT_DIR}/01_count_up.mp4"
    renderer.render(output, duration=5.0)
    print(f"  [OK] Saved to {output}")


def test_shake():
    """Test Shake effect for warning emphasis."""
    print("\n[2/10] Testing Shake effect - Hyperinflation Warning...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(25, 15, 15))

    # Warning label
    warning = Element(
        id="warning",
        element_type="text",
        text="WARNING: ECONOMIC COLLAPSE",
        font_size=64,
        color=(255, 80, 80),
        x='center',
        y=400,
    )
    warning.add_effects([
        FadeIn(start=0.2, duration=0.3),
        ScaleIn(start=0.2, duration=0.4, from_scale=0.9),
        Shake(start=0.6, duration=0.8, intensity=12, frequency=30, decay=True),
        Shake(start=2.0, duration=0.5, intensity=8, frequency=25, decay=True),
    ])
    renderer.add_element(warning)

    # Inflation number
    inflation = Element(
        id="inflation",
        element_type="text",
        text="1,000,000% INFLATION",
        font_size=48,
        color=(255, 200, 100),
        x='center',
        y=520,
    )
    inflation.add_effects([
        FadeIn(start=1.0, duration=0.5),
        Flash(start=1.5, duration=0.6, flashes=3),
    ])
    renderer.add_element(inflation)

    output = f"{OUTPUT_DIR}/02_shake.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_rotation():
    """Test rotation effects."""
    print("\n[3/10] Testing Rotation effects...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Spinning arrow icon
    arrow = Element(
        id="arrow",
        element_type="text",
        text="\u27F3",  # Clockwise arrow
        font_size=120,
        color=(100, 180, 255),
        x='center',
        y=350,
    )
    arrow.add_effects([
        FadeIn(start=0.2, duration=0.3),
        Spin(start=0.3, duration=2.0, rotations=2, clockwise=True, easing="ease_in_out_cubic"),
    ])
    renderer.add_element(arrow)

    # Rotating text with RotateIn
    rotating_text = Element(
        id="rotating",
        element_type="text",
        text="CRISIS CYCLE",
        font_size=48,
        color=(255, 255, 255),
        x='center',
        y=520,
    )
    rotating_text.add_effects([
        FadeIn(start=0.5, duration=0.5),
        RotateIn(start=0.5, duration=0.8, from_angle=-45, easing="ease_out_back"),
    ])
    renderer.add_element(rotating_text)

    # Wobbling element
    wobble_text = Element(
        id="wobble",
        element_type="text",
        text="Unstable",
        font_size=36,
        color=(255, 150, 100),
        x='center',
        y=650,
    )
    wobble_text.add_effects([
        FadeIn(start=1.0, duration=0.3),
        Wobble(start=1.3, duration=1.5, angle=20, oscillations=4),
    ])
    renderer.add_element(wobble_text)

    output = f"{OUTPUT_DIR}/03_rotation.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_blur():
    """Test blur effects - focus transitions."""
    print("\n[4/10] Testing Blur effects - Focus Pull...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Background text (starts blurred)
    bg_text = Element(
        id="bg_text",
        element_type="text",
        text="BACKGROUND",
        font_size=72,
        color=(60, 60, 80),
        x='center',
        y=350,
    )
    bg_text.add_effects([
        FadeIn(start=0.1, duration=0.2),
        BlurIn(start=0.1, duration=1.5, from_blur=15),  # Comes into focus
    ])
    renderer.add_element(bg_text)

    # Main text with focus pull
    main_text = Element(
        id="main",
        element_type="text",
        text="CHAVEZ ERA",
        font_size=96,
        color=(255, 255, 255),
        x='center',
        y=500,
    )
    main_text.add_effects([
        FadeIn(start=0.5, duration=0.3),
        FocusPull(start=0.5, duration=2.5, max_blur=10, focus_point=0.4),
    ])
    renderer.add_element(main_text)

    # Text that blurs out
    blur_out_text = Element(
        id="blur_out",
        element_type="text",
        text="1999 - 2013",
        font_size=36,
        color=(150, 150, 160),
        x='center',
        y=650,
    )
    blur_out_text.add_effects([
        FadeIn(start=1.0, duration=0.3),
        BlurOut(start=2.5, duration=1.0, to_blur=8),
    ])
    renderer.add_element(blur_out_text)

    output = f"{OUTPUT_DIR}/04_blur.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_shadow():
    """Test shadow effects."""
    print("\n[5/10] Testing Shadow effects...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(240, 235, 225))

    # Document title with shadow
    doc_title = Element(
        id="doc_title",
        element_type="text",
        text="DECREE No. 3,167",
        font_size=64,
        font_path="C:/Windows/Fonts/times.ttf",
        color=(40, 40, 60),
        x='center',
        y=400,
    )
    doc_title.add_effects([
        FadeIn(start=0.3, duration=0.5),
        ShadowIn(
            start=0.3, duration=0.8,
            offset=(6, 6), blur=10,
            color=(0, 0, 0), max_alpha=0.3
        ),
    ])
    renderer.add_element(doc_title)

    # Subtitle with pulsing shadow
    subtitle = Element(
        id="subtitle",
        element_type="text",
        text="Nationalization of Private Industry",
        font_size=32,
        color=(80, 80, 100),
        x='center',
        y=500,
    )
    subtitle.add_effects([
        FadeIn(start=0.8, duration=0.4),
        ShadowPulse(
            start=1.2, duration=2.0,
            offset=(4, 4), min_blur=4, max_blur=12,
            color=(0, 0, 0), alpha=0.25, pulses=2
        ),
    ])
    renderer.add_element(subtitle)

    output = f"{OUTPUT_DIR}/05_shadow.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_glow():
    """Test glow effects."""
    print("\n[6/10] Testing Glow effects - Neon Style...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(10, 10, 20))

    # Neon text with glow
    neon = Element(
        id="neon",
        element_type="text",
        text="CRISIS",
        font_size=120,
        color=(255, 50, 100),
        x='center',
        y=400,
    )
    neon.add_effects([
        FadeIn(start=0.2, duration=0.3),
        GlowIn(start=0.2, duration=0.8, radius=15, color=(255, 100, 150), max_alpha=0.7),
        GlowPulse(
            start=1.0, duration=2.5,
            min_radius=10, max_radius=20,
            color=(255, 100, 150),
            min_alpha=0.4, max_alpha=0.8,
            pulses=4
        ),
    ])
    renderer.add_element(neon)

    # Highlighted text
    highlight_text = Element(
        id="highlight",
        element_type="text",
        text="7 MILLION REFUGEES",
        font_size=48,
        color=(255, 220, 100),
        x='center',
        y=580,
    )
    highlight_text.add_effects([
        FadeIn(start=1.0, duration=0.3),
        Highlight(start=1.3, duration=1.0, radius=12, color=(255, 255, 200), peak_alpha=0.9),
    ])
    renderer.add_element(highlight_text)

    output = f"{OUTPUT_DIR}/06_glow.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_bounce_elastic():
    """Test bounce and elastic easing."""
    print("\n[7/10] Testing Bounce and Elastic easing...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Bouncy text
    bounce_text = Element(
        id="bounce",
        element_type="text",
        text="BOUNCE IN",
        font_size=64,
        color=(100, 200, 150),
        x='center',
        y=300,
    )
    bounce_text.add_effects([
        FadeIn(start=0.2, duration=0.2),
        SlideUp(start=0.2, duration=1.0, distance=100, easing="ease_out_bounce"),
    ])
    renderer.add_element(bounce_text)

    # Elastic text
    elastic_text = Element(
        id="elastic",
        element_type="text",
        text="ELASTIC SPRING",
        font_size=64,
        color=(200, 150, 255),
        x='center',
        y=450,
    )
    elastic_text.add_effects([
        FadeIn(start=0.5, duration=0.2),
        ScaleIn(start=0.5, duration=1.2, from_scale=0.5, easing="ease_out_elastic"),
    ])
    renderer.add_element(elastic_text)

    # Back easing (overshoot)
    back_text = Element(
        id="back",
        element_type="text",
        text="OVERSHOOT BACK",
        font_size=64,
        color=(255, 180, 100),
        x='center',
        y=600,
    )
    back_text.add_effects([
        FadeIn(start=1.0, duration=0.2),
        ScaleIn(start=1.0, duration=0.8, from_scale=0.7, easing="ease_out_back"),
    ])
    renderer.add_element(back_text)

    output = f"{OUTPUT_DIR}/07_bounce_elastic.mp4"
    renderer.render(output, duration=3.5)
    print(f"  [OK] Saved to {output}")


def test_glitch():
    """Test glitch effect."""
    print("\n[8/10] Testing Glitch effect - Digital Corruption...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(15, 15, 20))

    # Glitchy text
    glitch_text = Element(
        id="glitch",
        element_type="text",
        text="SYSTEM FAILURE",
        font_size=72,
        color=(255, 50, 50),
        x='center',
        y=450,
    )
    glitch_text.add_effects([
        FadeIn(start=0.2, duration=0.2),
        Glitch(start=0.3, duration=2.5, intensity=25, frequency=15),
    ])
    renderer.add_element(glitch_text)

    # Subtitle
    sub = Element(
        id="sub",
        element_type="text",
        text="Data Corrupted",
        font_size=32,
        color=(150, 150, 160),
        x='center',
        y=560,
    )
    sub.add_effects([
        FadeIn(start=0.8, duration=0.3),
        Glitch(start=1.0, duration=1.5, intensity=10, frequency=8),
    ])
    renderer.add_element(sub)

    output = f"{OUTPUT_DIR}/08_glitch.mp4"
    renderer.render(output, duration=4.0)
    print(f"  [OK] Saved to {output}")


def test_reveal():
    """Test word-by-word reveal effect."""
    print("\n[9/10] Testing Reveal effect - Word by Word...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(18, 18, 24))

    # Word reveal
    quote = Element(
        id="quote",
        element_type="text",
        text="The economy collapsed under socialist policies",
        font_size=48,
        color=(255, 255, 255),
        x='center',
        y=450,
    )
    quote.add_effects([
        Reveal(start=0.3, duration=2.5, mode="word", easing="linear"),
    ])
    renderer.add_element(quote)

    # Character reveal (typewriter style)
    typewriter = Element(
        id="typewriter",
        element_type="text",
        text="- Economic Analyst, 2019",
        font_size=28,
        color=(150, 150, 160),
        x='center',
        y=550,
    )
    typewriter.add_effects([
        Reveal(start=2.0, duration=1.5, mode="char", easing="linear"),
    ])
    renderer.add_element(typewriter)

    output = f"{OUTPUT_DIR}/09_reveal.mp4"
    renderer.render(output, duration=4.5)
    print(f"  [OK] Saved to {output}")


def test_combined():
    """Test combined effects for a dramatic reveal."""
    print("\n[10/10] Testing Combined effects - Dramatic Reveal...")

    renderer = BaseRenderer(width=1920, height=1080, fps=30, bg_color=(12, 12, 18))

    # Main stat with multiple effects
    stat = Element(
        id="stat",
        element_type="text",
        text="$0",  # Will be animated
        font_size=144,
        color=(255, 80, 80),
        x='center',
        y=400,
    )
    stat.add_effects([
        # Initial blur and scale in
        BlurIn(start=0.2, duration=0.8, from_blur=12),
        ScaleIn(start=0.2, duration=0.8, from_scale=0.6, easing="ease_out_back"),
        FadeIn(start=0.2, duration=0.5),
        # Count up the number
        CountUp(
            start=0.8, duration=2.5,
            from_value=0, to_value=7,
            prefix="", suffix=" Million",
            decimals=0,
            easing="ease_out_cubic"
        ),
        # Add glow at the end
        GlowIn(start=2.5, duration=0.8, radius=20, color=(255, 100, 100), max_alpha=0.5),
        # Shake for emphasis
        Shake(start=3.3, duration=0.5, intensity=6, frequency=20, decay=True),
    ])
    renderer.add_element(stat)

    # Label
    label = Element(
        id="label",
        element_type="text",
        text="REFUGEES",
        font_size=48,
        color=(200, 200, 210),
        x='center',
        y=550,
    )
    label.add_effects([
        FadeIn(start=1.0, duration=0.5),
        SlideUp(start=1.0, duration=0.6, distance=30, easing="ease_out_cubic"),
        ShadowIn(start=1.2, duration=0.6, offset=(3, 3), blur=6, color=(0, 0, 0), max_alpha=0.4),
    ])
    renderer.add_element(label)

    # Subtitle with highlight
    subtitle = Element(
        id="subtitle",
        element_type="text",
        text="The largest refugee crisis in Latin American history",
        font_size=28,
        color=(140, 140, 160),
        x='center',
        y=650,
    )
    subtitle.add_effects([
        FadeIn(start=2.0, duration=0.5),
        Highlight(start=2.5, duration=1.2, radius=8, color=(255, 200, 150), peak_alpha=0.6),
    ])
    renderer.add_element(subtitle)

    output = f"{OUTPUT_DIR}/10_combined.mp4"
    renderer.render(output, duration=5.0)
    print(f"  [OK] Saved to {output}")


def main():
    print("=" * 70)
    print("TESTING NEW EFFECTS WITH VENEZUELA CONTENT")
    print("=" * 70)

    test_count_up()
    test_shake()
    test_rotation()
    test_blur()
    test_shadow()
    test_glow()
    test_bounce_elastic()
    test_glitch()
    test_reveal()
    test_combined()

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETED!")
    print("=" * 70)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print("\nGenerated videos:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.mp4'):
            print(f"  - {f}")

    print("\n" + "=" * 70)
    print("New Effects Summary:")
    print("  - CountUp:     Animate numbers with prefix/suffix")
    print("  - Shake:       Emphasis shake with decay")
    print("  - Rotation:    RotateIn, Spin, Wobble")
    print("  - Blur:        BlurIn, BlurOut, FocusPull")
    print("  - Shadow:      ShadowIn, ShadowPulse")
    print("  - Glow:        GlowIn, GlowPulse, Highlight")
    print("  - Misc:        Flash, Glitch, Reveal, Bounce")
    print("  - Easing:      bounce, elastic, back (in/out/in-out)")
    print("=" * 70)


if __name__ == "__main__":
    main()
