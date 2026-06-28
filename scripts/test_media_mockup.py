#!/usr/bin/env python3
"""Test Media Mockup templates."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from nolan.renderer import (
    TweetCardRenderer,
    NewsHeadlineRenderer,
    DocumentHighlightRenderer,
)


def main():
    output_dir = project_root / "test_output" / "media_mockup"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Media Mockup Template Tests")
    print("=" * 60)

    # Test 1: Tweet Card
    print("\n[1/3] TweetCardRenderer...")
    renderer = TweetCardRenderer(
        username="Juan Guaido",
        handle="@jguaido",
        content="This is not a coup. This is a constitutional process.",
        timestamp="Jan 23, 2019",
        retweets="125K",
        likes="450K",
        verified=True
    )
    renderer.render(str(output_dir / "01_tweet_card.mp4"), duration=6.0)
    print("  [OK] Created 01_tweet_card.mp4")

    # Test 1b: Tweet without metrics
    print("\n[1b] TweetCardRenderer (simple)...")
    renderer = TweetCardRenderer(
        username="Reuters",
        handle="@Reuters",
        content="BREAKING: Venezuela inflation hits 1,000,000%",
        verified=True
    )
    renderer.render(str(output_dir / "01b_tweet_simple.mp4"), duration=5.0)
    print("  [OK] Created 01b_tweet_simple.mp4")

    # Test 2: News Headline
    print("\n[2/3] NewsHeadlineRenderer...")
    renderer = NewsHeadlineRenderer(
        headline="Venezuela declares state of emergency",
        source="Reuters",
        news_type="breaking"
    )
    renderer.render(str(output_dir / "02_news_headline.mp4"), duration=5.0)
    print("  [OK] Created 02_news_headline.mp4")

    # Test 2b: Different news types
    print("\n[2b] NewsHeadlineRenderer (exclusive)...")
    renderer = NewsHeadlineRenderer(
        headline="Secret documents reveal oil production fraud",
        source="Investigative Report",
        news_type="exclusive"
    )
    renderer.render(str(output_dir / "02b_news_exclusive.mp4"), duration=5.0)
    print("  [OK] Created 02b_news_exclusive.mp4")

    # Test 3: Document Highlight
    print("\n[3/3] DocumentHighlightRenderer...")
    renderer = DocumentHighlightRenderer(
        text="The government shall transfer ownership of all private enterprises to the state...",
        document_title="Decree No. 3,167",
        source="Official Gazette, March 2014"
    )
    renderer.render(str(output_dir / "03_document_highlight.mp4"), duration=6.0)
    print("  [OK] Created 03_document_highlight.mp4")

    # Test 3b: Document without title
    print("\n[3b] DocumentHighlightRenderer (simple)...")
    renderer = DocumentHighlightRenderer(
        text="Article 112: All economic activity shall be subject to state planning and control.",
        source="Constitution of Venezuela, 1999"
    )
    renderer.render(str(output_dir / "03b_document_simple.mp4"), duration=5.0)
    print("  [OK] Created 03b_document_simple.mp4")

    print("\n" + "=" * 60)
    print("All Media Mockup tests completed!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    # List all outputs
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("*.mp4")):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
