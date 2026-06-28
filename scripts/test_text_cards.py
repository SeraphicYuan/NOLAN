#!/usr/bin/env python3
"""Test new text card renderers."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    DefinitionRenderer,
    SourceCitationRenderer,
    PullQuoteRenderer,
    QuestionRenderer,
    VerdictRenderer,
)


def main():
    output_dir = project_root / "test_output" / "text_cards"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Text Card Renderer Tests")
    print("=" * 60)

    # Test 1: Definition
    print("\n[1/5] DefinitionRenderer...")
    renderer = DefinitionRenderer(
        term="Hyperinflation",
        definition="Extremely rapid or out of control inflation, typically exceeding 50% per month, leading to rapid devaluation of currency.",
        category="Economics"
    )
    renderer.render(str(output_dir / "01_definition.mp4"), duration=6.0)
    print("  [OK] Created 01_definition.mp4")

    # Test 2: Source Citation
    print("\n[2/5] SourceCitationRenderer...")
    renderer = SourceCitationRenderer(
        source_name="Venezuela's Economic Collapse Explained",
        publication="Reuters",
        date="March 15, 2019",
        author="Maria Santos"
    )
    renderer.render(str(output_dir / "02_source_citation.mp4"), duration=5.0)
    print("  [OK] Created 02_source_citation.mp4")

    # Test 3: Pull Quote
    print("\n[3/5] PullQuoteRenderer...")
    renderer = PullQuoteRenderer(
        quote="This is the biggest economic collapse in the history of the Western Hemisphere.",
        attribution="Dr. Ricardo Hausmann, Harvard Kennedy School"
    )
    renderer.render(str(output_dir / "03_pull_quote.mp4"), duration=6.0)
    print("  [OK] Created 03_pull_quote.mp4")

    # Test 4: Question
    print("\n[4/5] QuestionRenderer...")
    renderer = QuestionRenderer(
        question="What happens when a nation's wealth disappears overnight?",
        context="The Venezuelan Crisis"
    )
    renderer.render(str(output_dir / "04_question.mp4"), duration=5.0)
    print("  [OK] Created 04_question.mp4")

    # Test 5: Verdict (multiple types)
    print("\n[5/5] VerdictRenderer (3 types)...")

    # Conclusion
    renderer = VerdictRenderer(
        verdict="The economy never recovered from Chavez's policies",
        supporting_text="Despite multiple attempts at reform over two decades",
        verdict_type="conclusion"
    )
    renderer.render(str(output_dir / "05a_verdict_conclusion.mp4"), duration=5.0)
    print("  [OK] Created 05a_verdict_conclusion.mp4")

    # Warning
    renderer = VerdictRenderer(
        verdict="Inflation reached 1,000,000% in 2018",
        supporting_text="The highest rate ever recorded in the Americas",
        verdict_type="warning"
    )
    renderer.render(str(output_dir / "05b_verdict_warning.mp4"), duration=5.0)
    print("  [OK] Created 05b_verdict_warning.mp4")

    # Key Point
    renderer = VerdictRenderer(
        verdict="Oil accounts for 95% of Venezuela's export revenue",
        supporting_text="Making it extremely vulnerable to price fluctuations",
        verdict_type="key_point"
    )
    renderer.render(str(output_dir / "05c_verdict_keypoint.mp4"), duration=5.0)
    print("  [OK] Created 05c_verdict_keypoint.mp4")

    print("\n" + "=" * 60)
    print("All text card tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
