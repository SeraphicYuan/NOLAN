"""
Test portrait_reveal template with Venezuela documentary content.

Historical figures from the Venezuela documentary:
- Simón Bolívar - Independence hero
- Hugo Chávez - Bolivarian Revolution leader
- José Antonio Páez - Caudillo era strongman
- Juan Vicente Gómez - Oil-era dictator
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.scenes.portrait_reveal import render_portrait_reveal

OUTPUT_DIR = "test_output/venezuela_portraits"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_bolivar():
    """Simón Bolívar - The Liberator."""
    print("\n[1/4] Rendering Simón Bolívar portrait reveal...")

    output = f"{OUTPUT_DIR}/bolivar_reveal.mp4"

    render_portrait_reveal(
        title="The Liberator",
        points=[
            "Led independence from Spain",
            "Declared independence in 1821",
            "Vision of unified South America",
            "National hero of Venezuela",
        ],
        portrait_caption="Simón Bolívar",
        portrait_side="left",
        # Timing
        portrait_hold=1.5,
        slide_duration=0.8,
        point_interval=0.7,
        # Historical/sepia style
        bg_color=(20, 18, 15),
        border_color=(180, 150, 80),
        portrait_bg_color=(60, 55, 45),
        title_color=(220, 190, 120),
        title_size=64,
        point_color=(200, 195, 180),
        point_size=36,
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def test_chavez():
    """Hugo Chávez - Bolivarian Revolution."""
    print("\n[2/4] Rendering Hugo Chávez portrait reveal...")

    output = f"{OUTPUT_DIR}/chavez_reveal.mp4"

    render_portrait_reveal(
        title="Bolivarian Revolution",
        points=[
            "Rose to power in 1998",
            "Promised wealth redistribution",
            "Created parallel social programs",
            "Consolidated power after 2002 coup",
        ],
        portrait_caption="Hugo Chávez",
        portrait_side="left",
        # Modern/political style - red accent
        bg_color=(15, 12, 18),
        border_color=(180, 60, 60),
        portrait_bg_color=(50, 40, 45),
        title_color=(220, 80, 80),
        title_size=56,
        point_color=(220, 220, 230),
        point_size=34,
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def test_paez():
    """José Antonio Páez - Caudillo era."""
    print("\n[3/4] Rendering José Antonio Páez portrait reveal...")

    output = f"{OUTPUT_DIR}/paez_reveal.mp4"

    render_portrait_reveal(
        title="The Caudillo Era",
        points=[
            "Dominated 1830-1935 period",
            "Military strongman rule",
            "Prioritized local interests",
            "Fragmented national power",
        ],
        portrait_caption="José Antonio Páez",
        portrait_side="right",  # Test right side
        # Dark historical style
        bg_color=(12, 12, 16),
        border_color=(140, 120, 80),
        portrait_bg_color=(45, 42, 38),
        title_color=(180, 160, 100),
        title_size=56,
        point_color=(190, 185, 175),
        point_size=34,
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def test_oil_crisis():
    """Oil dependency - The economic trap."""
    print("\n[4/4] Rendering Oil Crisis portrait reveal...")

    output = f"{OUTPUT_DIR}/oil_crisis_reveal.mp4"

    render_portrait_reveal(
        title="The Oil Trap",
        points=[
            "1970s: Massive oil wealth",
            "1980s: Prices collapsed",
            "1989: Caracazo riots erupted",
            "Economy: House of cards",
        ],
        portrait_caption="Venezuela's Oil Industry",
        portrait_side="left",
        # Modern economic/danger style
        bg_color=(10, 10, 15),
        border_color=(200, 160, 60),
        portrait_bg_color=(40, 35, 30),
        title_color=(255, 200, 80),
        title_size=60,
        point_color=(230, 225, 210),
        point_size=36,
        # Faster timing for urgency
        portrait_hold=1.2,
        slide_duration=0.6,
        point_interval=0.6,
        output_path=output,
    )
    print(f"  [OK] Saved to {output}")


def main():
    print("=" * 60)
    print("TESTING PORTRAIT REVEAL - VENEZUELA DOCUMENTARY")
    print("=" * 60)

    test_bolivar()
    test_chavez()
    test_paez()
    test_oil_crisis()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print("\nGenerated videos:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.mp4'):
            print(f"  - {f}")


if __name__ == "__main__":
    main()
