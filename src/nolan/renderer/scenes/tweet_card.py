"""
Tweet card renderer.

Creates animated social media post mockups:
- Profile section (name, handle, optional avatar placeholder)
- Tweet text content
- Engagement metrics
- Timestamp

Animation: Card slides in, content fades in sequentially
"""

from typing import Tuple, Optional, Union
from ..base import BaseRenderer, Element
from ..effects import FadeIn, SlideUp
from ..layout import Position, POSITIONS


class TweetCardRenderer(BaseRenderer):
    """
    Render animated tweet/social media card mockups.

    Usage:
        renderer = TweetCardRenderer(
            username="Juan Guaido",
            handle="@jguaido",
            content="This is not a coup. This is a constitutional process.",
            timestamp="Jan 23, 2019",
            retweets="125K",
            likes="450K"
        )
        renderer.render("output.mp4", duration=6.0)
    """

    def __init__(
        self,
        content: str,
        username: str,
        handle: str,
        timestamp: str = None,
        retweets: str = None,
        likes: str = None,
        verified: bool = False,
        # Position
        position: Union[str, Position] = "center",
        # Visual style
        width: int = 1920,
        height: int = 1080,
        bg_color: Tuple[int, int, int] = (18, 18, 24),
        card_bg_color: Tuple[int, int, int] = (30, 34, 42),
        username_color: Tuple[int, int, int] = (255, 255, 255),
        handle_color: Tuple[int, int, int] = (120, 130, 150),
        content_color: Tuple[int, int, int] = (230, 230, 240),
        timestamp_color: Tuple[int, int, int] = (100, 110, 130),
        metric_color: Tuple[int, int, int] = (120, 130, 150),
        accent_color: Tuple[int, int, int] = (29, 161, 242),  # Twitter blue
        # Typography
        username_size: int = 28,
        handle_size: int = 22,
        content_size: int = 32,
        timestamp_size: int = 20,
        metric_size: int = 20,
        username_font: str = "C:/Windows/Fonts/arialbd.ttf",
        content_font: str = "C:/Windows/Fonts/arial.ttf",
        # Dimensions
        card_width: int = 700,
        card_padding: int = 30,
        # Timing
        fps: int = 30,
    ):
        super().__init__(width=width, height=height, fps=fps, bg_color=bg_color)

        # Resolve position
        if isinstance(position, str):
            self.position = POSITIONS.get(position, POSITIONS["center"])
        else:
            self.position = position

        self.content = content
        self.username = username
        self.handle = handle
        self.timestamp = timestamp
        self.retweets = retweets
        self.likes = likes
        self.verified = verified
        self.card_bg_color = card_bg_color
        self.username_color = username_color
        self.handle_color = handle_color
        self.content_color = content_color
        self.timestamp_color = timestamp_color
        self.metric_color = metric_color
        self.accent_color = accent_color
        self.username_size = username_size
        self.handle_size = handle_size
        self.content_size = content_size
        self.timestamp_size = timestamp_size
        self.metric_size = metric_size
        self.username_font = username_font
        self.content_font = content_font
        self.card_width = card_width
        self.card_padding = card_padding
        self._setup_elements()

    def _setup_elements(self):
        """Create and configure scene elements."""
        base_y = int(self.height * self.position.y)
        card_x = (self.width - self.card_width) // 2
        content_x = card_x + self.card_padding

        current_y = base_y - 120

        # Card background
        card_height = 280
        card_element = Element(
            id="card_bg",
            element_type="rectangle",
            color=self.card_bg_color,
            x=card_x,
            y=current_y - 20,
            width=self.card_width,
            height=card_height,
        )
        card_element.add_effects([
            FadeIn(start=0.2, duration=0.4, easing="ease_out_cubic"),
            SlideUp(start=0.2, duration=0.4, distance=20, easing="ease_out_cubic"),
        ])
        self.add_element(card_element)

        # Avatar placeholder (circle represented as small square for now)
        avatar_size = 50
        avatar_element = Element(
            id="avatar",
            element_type="rectangle",
            color=self.accent_color,
            x=content_x,
            y=current_y,
            width=avatar_size,
            height=avatar_size,
        )
        avatar_element.add_effect(
            FadeIn(start=0.4, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(avatar_element)

        # Username
        name_x = content_x + avatar_size + 15
        username_element = Element(
            id="username",
            element_type="text",
            text=self.username + (" \u2713" if self.verified else ""),
            font_path=self.username_font,
            font_size=self.username_size,
            color=self.username_color,
            x=name_x,
            y=current_y,
        )
        username_element.add_effect(
            FadeIn(start=0.5, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(username_element)

        # Handle
        handle_element = Element(
            id="handle",
            element_type="text",
            text=self.handle,
            font_path=self.content_font,
            font_size=self.handle_size,
            color=self.handle_color,
            x=name_x,
            y=current_y + self.username_size + 5,
        )
        handle_element.add_effect(
            FadeIn(start=0.55, duration=0.3, easing="ease_out_cubic")
        )
        self.add_element(handle_element)

        # Content (with smart wrapping)
        content_y = current_y + avatar_size + 20
        content_element = Element(
            id="content",
            element_type="text",
            text=self.content,
            font_path=self.content_font,
            font_size=self.content_size,
            color=self.content_color,
            x=content_x,
            y=content_y,
            max_width=self.card_width - self.card_padding * 2,
            max_lines=4,
            text_align="left",
        )
        content_element.add_effect(
            FadeIn(start=0.6, duration=0.5, easing="ease_out_cubic")
        )
        self.add_element(content_element)

        # Bottom metrics line
        metrics_y = content_y + 100

        # Timestamp
        if self.timestamp:
            timestamp_element = Element(
                id="timestamp",
                element_type="text",
                text=self.timestamp,
                font_path=self.content_font,
                font_size=self.timestamp_size,
                color=self.timestamp_color,
                x=content_x,
                y=metrics_y,
            )
            timestamp_element.add_effect(
                FadeIn(start=0.9, duration=0.3, easing="ease_out_cubic")
            )
            self.add_element(timestamp_element)

        # Metrics
        metric_x = content_x + 200
        if self.retweets:
            rt_element = Element(
                id="retweets",
                element_type="text",
                text=f"\u21bb {self.retweets}",  # Retweet symbol
                font_path=self.content_font,
                font_size=self.metric_size,
                color=self.metric_color,
                x=metric_x,
                y=metrics_y,
            )
            rt_element.add_effect(
                FadeIn(start=1.0, duration=0.3, easing="ease_out_cubic")
            )
            self.add_element(rt_element)

        if self.likes:
            likes_element = Element(
                id="likes",
                element_type="text",
                text=f"\u2665 {self.likes}",  # Heart symbol
                font_path=self.content_font,
                font_size=self.metric_size,
                color=self.metric_color,
                x=metric_x + 120,
                y=metrics_y,
            )
            likes_element.add_effect(
                FadeIn(start=1.1, duration=0.3, easing="ease_out_cubic")
            )
            self.add_element(likes_element)


def render_tweet_card(
    content: str,
    username: str,
    handle: str,
    output_path: str = "tweet.mp4",
    duration: float = 6.0,
    **style_kwargs,
) -> str:
    """Render an animated tweet card mockup."""
    renderer = TweetCardRenderer(content, username, handle, **style_kwargs)
    return renderer.render(output_path, duration=duration)
