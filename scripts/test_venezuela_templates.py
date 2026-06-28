#!/usr/bin/env python3
"""Test all 15 new templates with Venezuela documentary content."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    # Text Cards
    DefinitionRenderer,
    SourceCitationRenderer,
    PullQuoteRenderer,
    QuestionRenderer,
    VerdictRenderer,
    # Location/Time
    LocationStampRenderer,
    ChapterCardRenderer,
    ProgressBarRenderer,
    # Data Visualization
    StatComparisonRenderer,
    PercentageBarRenderer,
    RankingRenderer,
    # Media Mockup
    TweetCardRenderer,
    NewsHeadlineRenderer,
    DocumentHighlightRenderer,
    # Transitions
    SectionDividerRenderer,
)


def main():
    output_dir = project_root / "test_output" / "venezuela_templates"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Venezuela Documentary - Template Test Suite")
    print("Testing all 15 new templates with real documentary content")
    print("=" * 70)

    # =========================================================================
    # TEXT CARDS
    # =========================================================================
    print("\n" + "=" * 70)
    print("TEXT CARD TEMPLATES")
    print("=" * 70)

    # 1. Definition
    print("\n[01/15] DefinitionRenderer - Hyperinflation...")
    renderer = DefinitionRenderer(
        term="Hyperinflation",
        definition="Extremely rapid inflation, typically exceeding 50% per month, leading to the collapse of a currency's purchasing power.",
        category="Economics"
    )
    renderer.render(str(output_dir / "01_definition.mp4"), duration=6.0)
    print("  [OK]")

    # 2. Source Citation
    print("\n[02/15] SourceCitationRenderer - IMF Report...")
    renderer = SourceCitationRenderer(
        source_name="World Economic Outlook: Venezuela Analysis",
        publication="International Monetary Fund",
        date="October 2018",
        author="IMF Research Department"
    )
    renderer.render(str(output_dir / "02_source_citation.mp4"), duration=5.0)
    print("  [OK]")

    # 3. Pull Quote
    print("\n[03/15] PullQuoteRenderer - Hausmann Quote...")
    renderer = PullQuoteRenderer(
        quote="This is the single largest economic collapse outside of war in at least 45 years.",
        attribution="Ricardo Hausmann, Harvard Kennedy School"
    )
    renderer.render(str(output_dir / "03_pull_quote.mp4"), duration=6.0)
    print("  [OK]")

    # 4. Question
    print("\n[04/15] QuestionRenderer - Opening Question...")
    renderer = QuestionRenderer(
        question="How did the richest country in South America become one of the poorest?",
        context="The Venezuelan Collapse"
    )
    renderer.render(str(output_dir / "04_question.mp4"), duration=5.0)
    print("  [OK]")

    # 5. Verdict
    print("\n[05/15] VerdictRenderer - Conclusion...")
    renderer = VerdictRenderer(
        verdict="The Bolivarian Revolution destroyed Venezuela's economy",
        supporting_text="GDP fell 75% between 2013 and 2021",
        verdict_type="conclusion"
    )
    renderer.render(str(output_dir / "05_verdict.mp4"), duration=5.0)
    print("  [OK]")

    # =========================================================================
    # LOCATION/TIME
    # =========================================================================
    print("\n" + "=" * 70)
    print("LOCATION/TIME TEMPLATES")
    print("=" * 70)

    # 6. Location Stamp
    print("\n[06/15] LocationStampRenderer - Caracas...")
    renderer = LocationStampRenderer(
        location="Caracas, Venezuela",
        sublocation="Miraflores Palace",
        date="February 2, 1999"
    )
    renderer.render(str(output_dir / "06_location_stamp.mp4"), duration=5.0)
    print("  [OK]")

    # 7. Chapter Card
    print("\n[07/15] ChapterCardRenderer - Part II...")
    renderer = ChapterCardRenderer(
        title="The Collapse",
        chapter_number="Part II",
        subtitle="2013 - 2019"
    )
    renderer.render(str(output_dir / "07_chapter_card.mp4"), duration=5.0)
    print("  [OK]")

    # 8. Progress Bar
    print("\n[08/15] ProgressBarRenderer - Documentary Progress...")
    renderer = ProgressBarRenderer(
        progress=0.40,
        label="Documentary Progress",
        bar_fill_color=(255, 180, 100)
    )
    renderer.render(str(output_dir / "08_progress_bar.mp4"), duration=4.0)
    print("  [OK]")

    # =========================================================================
    # DATA VISUALIZATION
    # =========================================================================
    print("\n" + "=" * 70)
    print("DATA VISUALIZATION TEMPLATES")
    print("=" * 70)

    # 9. Stat Comparison
    print("\n[09/15] StatComparisonRenderer - GDP Collapse...")
    renderer = StatComparisonRenderer(
        left_value="$482B",
        left_label="GDP 2014",
        right_value="$106B",
        right_label="GDP 2020",
        title="Economic Freefall",
        left_color=(100, 200, 120),
        right_color=(255, 80, 80)
    )
    renderer.render(str(output_dir / "09_stat_comparison.mp4"), duration=6.0)
    print("  [OK]")

    # 10. Percentage Bar
    print("\n[10/15] PercentageBarRenderer - Poverty Rate...")
    renderer = PercentageBarRenderer(
        percentage=96,
        label="Population Living in Poverty",
        context="ENCOVI Survey, 2021",
        bar_fill_color=(255, 80, 80)
    )
    renderer.render(str(output_dir / "10_percentage_bar.mp4"), duration=5.0)
    print("  [OK]")

    # 11. Ranking
    print("\n[11/15] RankingRenderer - Refugee Crisis...")
    renderer = RankingRenderer(
        title="Venezuelan Refugees by Destination",
        items=[
            ("Colombia", "1.8 million"),
            ("Peru", "1.3 million"),
            ("Chile", "448,000"),
            ("Ecuador", "362,000"),
            ("Brazil", "261,000"),
        ]
    )
    renderer.render(str(output_dir / "11_ranking.mp4"), duration=7.0)
    print("  [OK]")

    # =========================================================================
    # MEDIA MOCKUP
    # =========================================================================
    print("\n" + "=" * 70)
    print("MEDIA MOCKUP TEMPLATES")
    print("=" * 70)

    # 12. Tweet Card
    print("\n[12/15] TweetCardRenderer - Guaido Tweet...")
    renderer = TweetCardRenderer(
        username="Juan Guaido",
        handle="@jguaido",
        content="Today I assume the role of interim president. The constitution demands it. The people demand it.",
        timestamp="Jan 23, 2019",
        retweets="89.2K",
        likes="312K",
        verified=True
    )
    renderer.render(str(output_dir / "12_tweet_card.mp4"), duration=6.0)
    print("  [OK]")

    # 13. News Headline
    print("\n[13/15] NewsHeadlineRenderer - Breaking News...")
    renderer = NewsHeadlineRenderer(
        headline="Venezuela inflation hits 1,000,000% as economy collapses",
        source="Reuters",
        news_type="breaking"
    )
    renderer.render(str(output_dir / "13_news_headline.mp4"), duration=5.0)
    print("  [OK]")

    # 14. Document Highlight
    print("\n[14/15] DocumentHighlightRenderer - Decree...")
    renderer = DocumentHighlightRenderer(
        text="The State shall promote and protect national industry... through expropriation of strategic assets.",
        document_title="Enabling Law Decree",
        source="Official Gazette No. 6.154, November 2014"
    )
    renderer.render(str(output_dir / "14_document_highlight.mp4"), duration=6.0)
    print("  [OK]")

    # =========================================================================
    # TRANSITIONS
    # =========================================================================
    print("\n" + "=" * 70)
    print("TRANSITION TEMPLATES")
    print("=" * 70)

    # 15. Section Divider
    print("\n[15/15] SectionDividerRenderer - Part III...")
    renderer = SectionDividerRenderer(
        title="The Exodus",
        section_number="Part III",
        subtitle="7 Million Fled",
        style="dramatic"
    )
    renderer.render(str(output_dir / "15_section_divider.mp4"), duration=4.0)
    print("  [OK]")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("ALL 15 TEMPLATES COMPLETED!")
    print("=" * 70)
    print(f"\nOutput directory: {output_dir}")
    print("\nGenerated videos:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")

    print("\n" + "=" * 70)
    print("Template Categories Summary:")
    print("  - Text Cards:         5 templates (01-05)")
    print("  - Location/Time:      3 templates (06-08)")
    print("  - Data Visualization: 3 templates (09-11)")
    print("  - Media Mockup:       3 templates (12-14)")
    print("  - Transitions:        1 template  (15)")
    print("=" * 70)


if __name__ == "__main__":
    main()
