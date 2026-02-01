# NOLAN Renderer Module
"""
Animated scene rendering system for video production.

Usage:
    from nolan.renderer import QuoteRenderer, TitleRenderer

    # Render an animated quote
    renderer = QuoteRenderer(
        quote="WE ARE TIRED",
        attribution="— Maria Rodriguez"
    )
    renderer.render("output.mp4", duration=7.0)

    # Or use presets
    from nolan.renderer.presets import documentary_quote
    documentary_quote("WE ARE TIRED", "— Maria", "output.mp4")
"""

from .base import BaseRenderer, Element, Timeline
from .easing import Easing
from .effects import FadeIn, FadeOut, SlideUp, SlideDown, ScaleIn, ExpandWidth
from .scenes.quote import QuoteRenderer
from .scenes.title import TitleRenderer
from .scenes.statistic import StatisticRenderer
from .scenes.list import ListRenderer
from .scenes.lower_third import LowerThirdRenderer
from .scenes.counter import CounterRenderer
from .scenes.comparison import ComparisonRenderer
from .scenes.ken_burns import KenBurnsRenderer
from .scenes.timeline import TimelineRenderer, TimelineEvent
from .scenes.flashback import FlashbackRenderer
from .scenes.definition import DefinitionRenderer
from .scenes.source_citation import SourceCitationRenderer
from .scenes.pull_quote import PullQuoteRenderer
from .scenes.question import QuestionRenderer
from .scenes.verdict import VerdictRenderer
from .scenes.location_stamp import LocationStampRenderer
from .scenes.chapter_card import ChapterCardRenderer
from .scenes.progress_bar import ProgressBarRenderer
from .scenes.stat_comparison import StatComparisonRenderer
from .scenes.percentage_bar import PercentageBarRenderer
from .scenes.ranking import RankingRenderer
from .scenes.tweet_card import TweetCardRenderer
from .scenes.news_headline import NewsHeadlineRenderer
from .scenes.document_highlight import DocumentHighlightRenderer
from .scenes.section_divider import SectionDividerRenderer
from .engine import PythonTemplateEngine, RenderResult, PYTHON_RENDERABLE_TYPES
from .layout import Position, POSITIONS, resolve_position

__all__ = [
    # Core
    'BaseRenderer',
    'Element',
    'Timeline',
    'Easing',
    # Effects
    'FadeIn',
    'FadeOut',
    'SlideUp',
    'SlideDown',
    'ScaleIn',
    'ExpandWidth',
    # Scene Renderers
    'QuoteRenderer',
    'TitleRenderer',
    'StatisticRenderer',
    'ListRenderer',
    'LowerThirdRenderer',
    'CounterRenderer',
    'ComparisonRenderer',
    'KenBurnsRenderer',
    'TimelineRenderer',
    'TimelineEvent',
    'FlashbackRenderer',
    # Text Card Renderers
    'DefinitionRenderer',
    'SourceCitationRenderer',
    'PullQuoteRenderer',
    'QuestionRenderer',
    'VerdictRenderer',
    # Location/Time Renderers
    'LocationStampRenderer',
    'ChapterCardRenderer',
    'ProgressBarRenderer',
    # Data Visualization Renderers
    'StatComparisonRenderer',
    'PercentageBarRenderer',
    'RankingRenderer',
    # Media Mockup Renderers
    'TweetCardRenderer',
    'NewsHeadlineRenderer',
    'DocumentHighlightRenderer',
    # Transition Renderers
    'SectionDividerRenderer',
    # Engine
    'PythonTemplateEngine',
    'RenderResult',
    'PYTHON_RENDERABLE_TYPES',
    # Layout
    'Position',
    'POSITIONS',
    'resolve_position',
]
