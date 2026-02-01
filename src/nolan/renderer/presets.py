"""
Pre-configured rendering presets for common scene types.

These provide one-line rendering for typical documentary/video essay scenes.
"""

from typing import Tuple
from pathlib import Path


# Documentary style colors
DOCUMENTARY_DARK = (26, 26, 26)
DOCUMENTARY_RED = (220, 38, 38)
HISTORICAL_BG = (20, 18, 15)
HISTORICAL_GOLD = (180, 140, 80)


def documentary_quote(
    quote: str,
    attribution: str,
    output_path: str,
    duration: float = 7.0,
) -> str:
    """
    Render a documentary-style quote card.

    Dark background, white text, red accent bar.
    """
    from .scenes.quote import QuoteRenderer

    renderer = QuoteRenderer(
        quote=quote,
        attribution=attribution,
        bg_color=DOCUMENTARY_DARK,
        quote_color=(255, 255, 255),
        attr_color=(136, 136, 136),
        accent_color=DOCUMENTARY_RED,
    )
    return renderer.render(output_path, duration=duration)


def documentary_title(
    title: str,
    subtitle: str = None,
    output_path: str = "title.mp4",
    duration: float = 6.0,
) -> str:
    """
    Render a documentary-style title card.

    Near-black background, white title, red accent line.
    """
    from .scenes.title import TitleRenderer

    renderer = TitleRenderer(
        title=title,
        subtitle=subtitle,
        bg_color=(15, 15, 20),
        title_color=(255, 255, 255),
        subtitle_color=(180, 180, 180),
        accent_color=DOCUMENTARY_RED,
    )
    return renderer.render(output_path, duration=duration)


def historical_year(
    year: str,
    label: str = None,
    output_path: str = "year.mp4",
    duration: float = 5.0,
) -> str:
    """
    Render a historical year reveal.

    Sepia tones, gold accents - perfect for historical documentaries.
    """
    from .scenes.statistic import StatisticRenderer

    renderer = StatisticRenderer(
        value=year,
        label=label,
        bg_color=HISTORICAL_BG,
        value_color=(255, 255, 255),
        label_color=(200, 180, 140),
        accent_color=HISTORICAL_GOLD,
        value_size=200,
    )
    return renderer.render(output_path, duration=duration)


def big_number(
    number: str,
    label: str,
    output_path: str = "stat.mp4",
    duration: float = 5.0,
    prefix: str = "",
    suffix: str = "",
    style: str = "modern",  # "modern", "danger", "success"
) -> str:
    """
    Render a big number/statistic reveal.

    Perfect for "300 BILLION BARRELS" type statistics.
    """
    from .scenes.statistic import StatisticRenderer

    renderer = StatisticRenderer(
        value=number,
        label=label,
        prefix=prefix,
        suffix=suffix,
        value_size=140,
        label_size=42,
    )

    if style == "danger":
        renderer.with_danger_style()
    elif style == "modern":
        renderer.with_modern_style()
    # else: use default historical style

    return renderer.render(output_path, duration=duration)


def topic_list(
    title: str,
    items: list,
    output_path: str = "topics.mp4",
    duration: float = 6.0,
    show_numbers: bool = True,
) -> str:
    """
    Render a topic/agenda list.

    Perfect for "We'll explore three themes: 1. History, 2. Economy, 3. Politics"
    """
    from .scenes.list import ListRenderer

    renderer = ListRenderer(
        title=title,
        items=items,
        show_numbers=show_numbers,
        bg_color=(15, 15, 20),
        title_color=(255, 255, 255),
        item_color=(200, 200, 210),
        accent_color=DOCUMENTARY_RED,
    )
    return renderer.render(output_path, duration=duration)


def chapter_title(
    chapter: str,
    title: str,
    output_path: str = "chapter.mp4",
    duration: float = 5.0,
) -> str:
    """
    Render a chapter title card.

    Chapter number small above, title large below.
    """
    from .scenes.title import TitleRenderer

    # Use chapter as "subtitle" position, title as main
    # Note: This is a bit of a hack - ideally we'd have a ChapterRenderer
    renderer = TitleRenderer(
        title=title,
        subtitle=f"CHAPTER {chapter}",
        bg_color=(10, 10, 15),
        title_color=(255, 255, 255),
        subtitle_color=(100, 100, 120),
        accent_color=(70, 130, 220),
        title_size=72,
        subtitle_size=24,
    )
    return renderer.render(output_path, duration=duration)


# Style presets that can be applied to any renderer
class StylePresets:
    """Color/style presets for renderers."""

    @staticmethod
    def documentary() -> dict:
        """Dark documentary style."""
        return {
            'bg_color': (26, 26, 26),
            'title_color': (255, 255, 255),
            'subtitle_color': (150, 150, 150),
            'accent_color': (220, 38, 38),
        }

    @staticmethod
    def historical() -> dict:
        """Sepia/historical style."""
        return {
            'bg_color': (20, 18, 15),
            'title_color': (255, 250, 240),
            'subtitle_color': (200, 180, 140),
            'accent_color': (180, 140, 80),
        }

    @staticmethod
    def modern_clean() -> dict:
        """Clean modern style."""
        return {
            'bg_color': (250, 250, 252),
            'title_color': (30, 30, 40),
            'subtitle_color': (100, 100, 110),
            'accent_color': (70, 130, 220),
        }

    @staticmethod
    def danger() -> dict:
        """Warning/danger style."""
        return {
            'bg_color': (25, 15, 15),
            'title_color': (255, 80, 80),
            'subtitle_color': (180, 150, 150),
            'accent_color': (200, 60, 60),
        }

    @staticmethod
    def success() -> dict:
        """Success/positive style."""
        return {
            'bg_color': (15, 25, 20),
            'title_color': (80, 220, 120),
            'subtitle_color': (150, 180, 160),
            'accent_color': (60, 180, 100),
        }
