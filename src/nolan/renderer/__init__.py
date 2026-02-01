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
    # Engine
    'PythonTemplateEngine',
    'RenderResult',
    'PYTHON_RENDERABLE_TYPES',
    # Layout
    'Position',
    'POSITIONS',
    'resolve_position',
]
