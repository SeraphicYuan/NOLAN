"""
Layout and positioning system for Python renderer.

Provides named position presets and percentage-based positioning
that aligns with the render-service layout system.

Usage:
    from nolan.renderer.layout import Position, POSITIONS

    # Named preset
    pos = Position.from_preset("lower-third")

    # Custom percentage
    pos = Position(x=0.5, y=0.8, align="center", valign="middle")

    # Resolve to pixels
    x, y = pos.resolve(width=1920, height=1080, element_width=400, element_height=100)
"""

from dataclasses import dataclass
from typing import Literal, Union, Dict, Any, Tuple


Align = Literal["left", "center", "right"]
VAlign = Literal["top", "middle", "bottom"]


@dataclass
class Position:
    """
    Position specification for elements.

    Coordinates are percentages (0-1) where:
    - x=0 is left edge, x=1 is right edge
    - y=0 is top edge, y=1 is bottom edge

    Alignment determines how the element is anchored:
    - align="left": element's left edge at x position
    - align="center": element's center at x position
    - align="right": element's right edge at x position
    """
    x: float = 0.5          # Horizontal position (0-1)
    y: float = 0.5          # Vertical position (0-1)
    align: Align = "center"  # Horizontal alignment
    valign: VAlign = "middle"  # Vertical alignment
    padding: float = 0.05   # Safe margin from edges (percentage)

    def resolve(
        self,
        canvas_width: int,
        canvas_height: int,
        element_width: int = 0,
        element_height: int = 0,
    ) -> Tuple[int, int]:
        """
        Convert percentage position to pixel coordinates.

        Args:
            canvas_width: Total canvas width in pixels
            canvas_height: Total canvas height in pixels
            element_width: Width of element being positioned
            element_height: Height of element being positioned

        Returns:
            Tuple of (x, y) pixel coordinates for element's top-left corner
        """
        # Calculate safe area
        safe_left = int(canvas_width * self.padding)
        safe_top = int(canvas_height * self.padding)
        safe_width = canvas_width - (2 * safe_left)
        safe_height = canvas_height - (2 * safe_top)

        # Base position within safe area
        base_x = safe_left + int(safe_width * self.x)
        base_y = safe_top + int(safe_height * self.y)

        # Adjust for horizontal alignment
        if self.align == "center":
            final_x = base_x - (element_width // 2)
        elif self.align == "right":
            final_x = base_x - element_width
        else:  # left
            final_x = base_x

        # Adjust for vertical alignment
        if self.valign == "middle":
            final_y = base_y - (element_height // 2)
        elif self.valign == "bottom":
            final_y = base_y - element_height
        else:  # top
            final_y = base_y

        return final_x, final_y

    @classmethod
    def from_preset(cls, name: str) -> 'Position':
        """Create position from named preset."""
        if name not in POSITIONS:
            raise ValueError(f"Unknown position preset: {name}. Available: {list(POSITIONS.keys())}")
        return POSITIONS[name]

    @classmethod
    def from_spec(cls, spec: Union[str, Dict[str, Any], 'Position']) -> 'Position':
        """
        Create position from various input formats.

        Args:
            spec: Can be:
                - str: preset name like "center", "lower-third"
                - dict: {"x": 0.5, "y": 0.8, "align": "center"}
                - Position: returned as-is
        """
        if isinstance(spec, Position):
            return spec
        if isinstance(spec, str):
            return cls.from_preset(spec)
        if isinstance(spec, dict):
            return cls(**spec)
        raise ValueError(f"Invalid position spec: {spec}")


# Named position presets (aligned with render-service layout templates)
POSITIONS: Dict[str, Position] = {
    # Centered positions
    "center": Position(x=0.5, y=0.5, align="center", valign="middle"),
    "center-top": Position(x=0.5, y=0.2, align="center", valign="middle"),
    "center-bottom": Position(x=0.5, y=0.8, align="center", valign="middle"),

    # Lower third (for speaker IDs, citations)
    "lower-third": Position(x=0.5, y=0.85, align="center", valign="middle", padding=0.03),
    "lower-third-left": Position(x=0.05, y=0.85, align="left", valign="middle", padding=0.03),
    "lower-third-right": Position(x=0.95, y=0.85, align="right", valign="middle", padding=0.03),

    # Upper third (for chapter titles, labels)
    "upper-third": Position(x=0.5, y=0.15, align="center", valign="middle", padding=0.03),
    "upper-third-left": Position(x=0.05, y=0.15, align="left", valign="middle", padding=0.03),
    "upper-third-right": Position(x=0.95, y=0.15, align="right", valign="middle", padding=0.03),

    # Corners
    "top-left": Position(x=0.0, y=0.0, align="left", valign="top"),
    "top-right": Position(x=1.0, y=0.0, align="right", valign="top"),
    "bottom-left": Position(x=0.0, y=1.0, align="left", valign="bottom"),
    "bottom-right": Position(x=1.0, y=1.0, align="right", valign="bottom"),

    # Split screen positions
    "left-half": Position(x=0.25, y=0.5, align="center", valign="middle"),
    "right-half": Position(x=0.75, y=0.5, align="center", valign="middle"),

    # Full screen with margins
    "full": Position(x=0.5, y=0.5, align="center", valign="middle", padding=0.05),
}


# Convenience function
def resolve_position(
    position: Union[str, Dict, Position],
    canvas_width: int,
    canvas_height: int,
    element_width: int = 0,
    element_height: int = 0,
) -> Tuple[int, int]:
    """
    Resolve any position specification to pixel coordinates.

    Args:
        position: Preset name, dict, or Position object
        canvas_width: Canvas width in pixels
        canvas_height: Canvas height in pixels
        element_width: Element width for alignment calculation
        element_height: Element height for alignment calculation

    Returns:
        Tuple of (x, y) pixel coordinates
    """
    pos = Position.from_spec(position)
    return pos.resolve(canvas_width, canvas_height, element_width, element_height)
