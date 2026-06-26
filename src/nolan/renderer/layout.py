"""
Layout System for NOLAN

This module provides two complementary positioning systems:

1. **Position** - Percentage-based positioning for single elements
   - Simple placement using x/y percentages (0-1)
   - Named presets: "center", "lower-third", "top-left", etc.
   - Good for overlays, text, simple compositions

2. **Layout/Slot** - Region-based screen division
   - Divides screen into slots (columns, rows, grids)
   - Cross-platform: works with Python, Motion Canvas, Remotion
   - Good for complex compositions, split screens, comparisons

Usage:
    # Position-based (single element)
    from nolan.renderer.layout import Position, POSITIONS
    pos = Position.from_preset("lower-third")
    x, y = pos.resolve(1920, 1080, element_width, element_height)

    # Layout-based (screen regions)
    from nolan.renderer.layout import Layout, Slot
    layout = Layout(width=1920, height=1080)
    left, right = layout.columns([1, 2])
    # Use left.x, left.width, right.inner_x, etc.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Literal, Dict, Any, Union
import json


# =============================================================================
# POSITION SYSTEM - Percentage-based element positioning
# =============================================================================

Align = Literal["left", "center", "right"]
VAlign = Literal["top", "middle", "bottom"]


@dataclass
class Position:
    """
    Position specification for elements using percentages.

    Coordinates are percentages (0-1) where:
    - x=0 is left edge, x=1 is right edge
    - y=0 is top edge, y=1 is bottom edge

    Alignment determines how the element is anchored:
    - align="left": element's left edge at x position
    - align="center": element's center at x position
    - align="right": element's right edge at x position

    Attributes:
        x: Horizontal position (0-1)
        y: Vertical position (0-1)
        align: Horizontal alignment
        valign: Vertical alignment
        padding: Safe margin from edges (percentage)
    """
    x: float = 0.5
    y: float = 0.5
    align: Align = "center"
    valign: VAlign = "middle"
    padding: float = 0.05

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


# Named position presets
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


# =============================================================================
# SLOT - A region of the screen
# =============================================================================

@dataclass
class Slot:
    """
    A rectangular region of the screen for content placement.

    Slots are the output of layout calculations. They provide:
    - Absolute position (x, y)
    - Dimensions (width, height)
    - Helper methods for alignment within the slot

    Attributes:
        x: Left edge x coordinate
        y: Top edge y coordinate
        width: Total width of the slot
        height: Total height of the slot
        padding: Inner padding (content should stay within padding)
        name: Optional name for the slot (e.g., "portrait", "content")
    """
    x: int
    y: int
    width: int
    height: int
    padding: int = 40
    name: Optional[str] = None

    # --- Computed Properties ---

    @property
    def center_x(self) -> int:
        """Horizontal center of the slot."""
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        """Vertical center of the slot."""
        return self.y + self.height // 2

    @property
    def right(self) -> int:
        """Right edge x coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Bottom edge y coordinate."""
        return self.y + self.height

    @property
    def inner_x(self) -> int:
        """Left edge of content area (after padding)."""
        return self.x + self.padding

    @property
    def inner_y(self) -> int:
        """Top edge of content area (after padding)."""
        return self.y + self.padding

    @property
    def inner_width(self) -> int:
        """Width available for content (minus padding)."""
        return self.width - self.padding * 2

    @property
    def inner_height(self) -> int:
        """Height available for content (minus padding)."""
        return self.height - self.padding * 2

    # --- Alignment Helpers ---

    def align_x(self, element_width: int, align: Literal["left", "center", "right"] = "center") -> int:
        """
        Get x position for an element aligned within this slot.

        Args:
            element_width: Width of the element to position
            align: Alignment mode

        Returns:
            x coordinate for the element's left edge
        """
        if align == "center":
            return self.x + (self.width - element_width) // 2
        elif align == "left":
            return self.x + self.padding
        else:  # right
            return self.x + self.width - self.padding - element_width

    def align_y(self, element_height: int, align: Literal["top", "center", "bottom"] = "center") -> int:
        """
        Get y position for an element aligned within this slot.

        Args:
            element_height: Height of the element to position
            align: Alignment mode

        Returns:
            y coordinate for the element's top edge
        """
        if align == "center":
            return self.y + (self.height - element_height) // 2
        elif align == "top":
            return self.y + self.padding
        else:  # bottom
            return self.y + self.height - self.padding - element_height

    def place(self, element_width: int, element_height: int,
              align_x: Literal["left", "center", "right"] = "center",
              align_y: Literal["top", "center", "bottom"] = "center") -> Tuple[int, int]:
        """
        Get (x, y) position for an element placed in this slot.

        Args:
            element_width: Width of the element
            element_height: Height of the element
            align_x: Horizontal alignment
            align_y: Vertical alignment

        Returns:
            Tuple of (x, y) coordinates
        """
        return (
            self.align_x(element_width, align_x),
            self.align_y(element_height, align_y)
        )

    # --- Subdivision ---

    def subdivide_rows(self, ratios: List[int], gap: int = 20) -> List['Slot']:
        """Divide this slot into rows."""
        total = sum(ratios)
        usable_height = self.inner_height - (len(ratios) - 1) * gap

        slots = []
        y = self.inner_y
        for i, ratio in enumerate(ratios):
            slot_height = int(usable_height * ratio / total)
            slots.append(Slot(
                x=self.inner_x,
                y=y,
                width=self.inner_width,
                height=slot_height,
                padding=0,  # Already inside padding
                name=f"{self.name}_row{i}" if self.name else None
            ))
            y += slot_height + gap
        return slots

    def subdivide_cols(self, ratios: List[int], gap: int = 20) -> List['Slot']:
        """Divide this slot into columns."""
        total = sum(ratios)
        usable_width = self.inner_width - (len(ratios) - 1) * gap

        slots = []
        x = self.inner_x
        for i, ratio in enumerate(ratios):
            slot_width = int(usable_width * ratio / total)
            slots.append(Slot(
                x=x,
                y=self.inner_y,
                width=slot_width,
                height=self.inner_height,
                padding=0,
                name=f"{self.name}_col{i}" if self.name else None
            ))
            x += slot_width + gap
        return slots

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (JSON-serializable)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Slot':
        """Create from dictionary."""
        return cls(**data)


# =============================================================================
# LAYOUT - Screen divider
# =============================================================================

@dataclass
class Layout:
    """
    Divides a screen into slots based on ratios and spacing.

    This is the main entry point for creating layouts. It handles:
    - Screen dimensions and safe zones
    - Column and row divisions
    - Grid layouts
    - Preset layouts (thirds, golden ratio, etc.)

    Example:
        layout = Layout(width=1920, height=1080)

        # Two columns, 1:2 ratio
        left, right = layout.columns([1, 2])

        # Three equal columns
        a, b, c = layout.columns([1, 1, 1])

        # 2x2 grid
        grid = layout.grid(2, 2)
        top_left = grid[0][0]

    Attributes:
        width: Total screen width
        height: Total screen height
        margin: Outer margin (space from screen edge)
        safe_zone: Additional safe zone for broadcast (usually 0 for web)
        default_gap: Default gap between slots
        default_padding: Default padding inside slots
    """
    width: int = 1920
    height: int = 1080
    margin: int = 100
    safe_zone: int = 0
    default_gap: int = 60
    default_padding: int = 40

    # --- Computed Properties ---

    @property
    def usable_x(self) -> int:
        """Left edge of usable area."""
        return self.margin + self.safe_zone

    @property
    def usable_y(self) -> int:
        """Top edge of usable area."""
        return self.margin + self.safe_zone

    @property
    def usable_width(self) -> int:
        """Width of usable area."""
        return self.width - 2 * (self.margin + self.safe_zone)

    @property
    def usable_height(self) -> int:
        """Height of usable area."""
        return self.height - 2 * (self.margin + self.safe_zone)

    # --- Layout Methods ---

    def full(self, name: str = "full") -> Slot:
        """
        Single slot covering the entire usable area.

        Returns:
            One Slot covering the full layout area
        """
        return Slot(
            x=self.usable_x,
            y=self.usable_y,
            width=self.usable_width,
            height=self.usable_height,
            padding=self.default_padding,
            name=name
        )

    def columns(self, ratios: List[int], gap: int = None,
                names: List[str] = None, padding: int = None) -> List[Slot]:
        """
        Divide screen into columns by ratio.

        Args:
            ratios: List of relative widths (e.g., [1, 2] for 1/3 + 2/3)
            gap: Space between columns (default: default_gap)
            names: Optional names for each slot
            padding: Padding inside each slot

        Returns:
            List of Slots, one per column

        Example:
            left, right = layout.columns([1, 2])  # 33% + 67%
            a, b, c = layout.columns([1, 1, 1])   # Equal thirds
        """
        if gap is None:
            gap = self.default_gap
        if padding is None:
            padding = self.default_padding
        if names is None:
            names = [f"col{i}" for i in range(len(ratios))]

        total = sum(ratios)
        num_gaps = len(ratios) - 1
        available_width = self.usable_width - num_gaps * gap

        slots = []
        x = self.usable_x
        for i, ratio in enumerate(ratios):
            slot_width = int(available_width * ratio / total)
            slots.append(Slot(
                x=x,
                y=self.usable_y,
                width=slot_width,
                height=self.usable_height,
                padding=padding,
                name=names[i] if i < len(names) else None
            ))
            x += slot_width + gap

        return slots

    def rows(self, ratios: List[int], gap: int = None,
             names: List[str] = None, padding: int = None) -> List[Slot]:
        """
        Divide screen into rows by ratio.

        Args:
            ratios: List of relative heights (e.g., [1, 3] for header + body)
            gap: Space between rows (default: default_gap)
            names: Optional names for each slot
            padding: Padding inside each slot

        Returns:
            List of Slots, one per row

        Example:
            header, body = layout.rows([1, 4])  # 20% + 80%
        """
        if gap is None:
            gap = self.default_gap
        if padding is None:
            padding = self.default_padding
        if names is None:
            names = [f"row{i}" for i in range(len(ratios))]

        total = sum(ratios)
        num_gaps = len(ratios) - 1
        available_height = self.usable_height - num_gaps * gap

        slots = []
        y = self.usable_y
        for i, ratio in enumerate(ratios):
            slot_height = int(available_height * ratio / total)
            slots.append(Slot(
                x=self.usable_x,
                y=y,
                width=self.usable_width,
                height=slot_height,
                padding=padding,
                name=names[i] if i < len(names) else None
            ))
            y += slot_height + gap

        return slots

    def grid(self, cols: int, rows: int, gap: int = None,
             padding: int = None) -> List[List[Slot]]:
        """
        Create a grid of slots.

        Args:
            cols: Number of columns
            rows: Number of rows
            gap: Space between cells
            padding: Padding inside each cell

        Returns:
            2D list of Slots: grid[row][col]

        Example:
            grid = layout.grid(2, 2)
            top_left = grid[0][0]
            bottom_right = grid[1][1]
        """
        if gap is None:
            gap = self.default_gap
        if padding is None:
            padding = self.default_padding

        # Calculate cell dimensions
        available_width = self.usable_width - (cols - 1) * gap
        available_height = self.usable_height - (rows - 1) * gap
        cell_width = available_width // cols
        cell_height = available_height // rows

        grid = []
        for row in range(rows):
            row_slots = []
            for col in range(cols):
                slot = Slot(
                    x=self.usable_x + col * (cell_width + gap),
                    y=self.usable_y + row * (cell_height + gap),
                    width=cell_width,
                    height=cell_height,
                    padding=padding,
                    name=f"cell_{row}_{col}"
                )
                row_slots.append(slot)
            grid.append(row_slots)

        return grid

    def grid_flat(self, cols: int, rows: int, gap: int = None,
                  padding: int = None) -> List[Slot]:
        """
        Create a grid of slots as a flat list (row-major order).

        Returns:
            List of Slots: [row0_col0, row0_col1, ..., row1_col0, ...]
        """
        grid = self.grid(cols, rows, gap, padding)
        return [slot for row in grid for slot in row]

    # --- Preset Layouts ---

    @classmethod
    def thirds(cls, **kwargs) -> List[Slot]:
        """Rule of thirds - three equal columns."""
        return cls(**kwargs).columns([1, 1, 1], names=["left", "center", "right"])

    @classmethod
    def split(cls, ratios: List[int] = [1, 2], **kwargs) -> List[Slot]:
        """Simple split layout."""
        return cls(**kwargs).columns(ratios)

    @classmethod
    def golden(cls, **kwargs) -> List[Slot]:
        """Golden ratio split (~38% / 62%)."""
        return cls(**kwargs).columns([38, 62], names=["minor", "major"])

    @classmethod
    def golden_reverse(cls, **kwargs) -> List[Slot]:
        """Reverse golden ratio (~62% / 38%)."""
        return cls(**kwargs).columns([62, 38], names=["major", "minor"])

    @classmethod
    def sidebar_left(cls, sidebar_width: int = 400, **kwargs) -> List[Slot]:
        """Fixed-width sidebar on left."""
        layout = cls(**kwargs)
        main_width = layout.usable_width - sidebar_width - layout.default_gap
        return [
            Slot(layout.usable_x, layout.usable_y, sidebar_width,
                 layout.usable_height, layout.default_padding, "sidebar"),
            Slot(layout.usable_x + sidebar_width + layout.default_gap, layout.usable_y,
                 main_width, layout.usable_height, layout.default_padding, "main")
        ]

    @classmethod
    def sidebar_right(cls, sidebar_width: int = 400, **kwargs) -> List[Slot]:
        """Fixed-width sidebar on right."""
        layout = cls(**kwargs)
        main_width = layout.usable_width - sidebar_width - layout.default_gap
        return [
            Slot(layout.usable_x, layout.usable_y, main_width,
                 layout.usable_height, layout.default_padding, "main"),
            Slot(layout.usable_x + main_width + layout.default_gap, layout.usable_y,
                 sidebar_width, layout.usable_height, layout.default_padding, "sidebar")
        ]

    # --- Schema Support ---

    def from_schema(self, schema: Dict[str, Any]) -> Union[Slot, List[Slot], List[List[Slot]]]:
        """
        Create layout from a schema dictionary.

        Schema format:
            {"type": "full"}
            {"type": "columns", "ratios": [1, 2], "gap": 60}
            {"type": "rows", "ratios": [1, 4]}
            {"type": "grid", "cols": 2, "rows": 2}
            {"type": "preset", "name": "golden"}

        Args:
            schema: Layout schema dictionary

        Returns:
            Slot(s) based on schema type
        """
        layout_type = schema.get("type", "full")

        if layout_type == "full":
            return self.full(schema.get("name", "full"))

        elif layout_type == "columns":
            return self.columns(
                ratios=schema["ratios"],
                gap=schema.get("gap", self.default_gap),
                names=schema.get("names"),
                padding=schema.get("padding", self.default_padding)
            )

        elif layout_type == "rows":
            return self.rows(
                ratios=schema["ratios"],
                gap=schema.get("gap", self.default_gap),
                names=schema.get("names"),
                padding=schema.get("padding", self.default_padding)
            )

        elif layout_type == "grid":
            return self.grid(
                cols=schema["cols"],
                rows=schema["rows"],
                gap=schema.get("gap", self.default_gap),
                padding=schema.get("padding", self.default_padding)
            )

        elif layout_type == "preset":
            preset_name = schema["name"]
            preset_func = getattr(self.__class__, preset_name, None)
            if preset_func:
                return preset_func(
                    width=self.width,
                    height=self.height,
                    margin=self.margin,
                    safe_zone=self.safe_zone
                )
            raise ValueError(f"Unknown preset: {preset_name}")

        else:
            raise ValueError(f"Unknown layout type: {layout_type}")

    def to_schema(self) -> Dict[str, Any]:
        """Export layout configuration as schema."""
        return {
            "width": self.width,
            "height": self.height,
            "margin": self.margin,
            "safe_zone": self.safe_zone,
            "default_gap": self.default_gap,
            "default_padding": self.default_padding
        }


# =============================================================================
# LAYOUT PRESETS - Common video essay layouts
# =============================================================================

LAYOUT_PRESETS = {
    # Basic splits
    "full": {"type": "full"},
    "half": {"type": "columns", "ratios": [1, 1]},
    "thirds": {"type": "columns", "ratios": [1, 1, 1]},
    "quarters": {"type": "columns", "ratios": [1, 1, 1, 1]},

    # Asymmetric splits
    "split-1-2": {"type": "columns", "ratios": [1, 2]},
    "split-2-1": {"type": "columns", "ratios": [2, 1]},
    "split-1-3": {"type": "columns", "ratios": [1, 3]},
    "split-3-1": {"type": "columns", "ratios": [3, 1]},

    # Golden ratio
    "golden": {"type": "preset", "name": "golden"},
    "golden-reverse": {"type": "preset", "name": "golden_reverse"},

    # Grids
    "grid-2x2": {"type": "grid", "cols": 2, "rows": 2},
    "grid-3x3": {"type": "grid", "cols": 3, "rows": 3},
    "grid-2x3": {"type": "grid", "cols": 3, "rows": 2},
    "grid-3x2": {"type": "grid", "cols": 2, "rows": 3},

    # Rows
    "header-body": {"type": "rows", "ratios": [1, 4]},
    "body-footer": {"type": "rows", "ratios": [4, 1]},
    "header-body-footer": {"type": "rows", "ratios": [1, 6, 1]},

    # Video essay specific
    "portrait-reveal": {"type": "columns", "ratios": [1, 2], "names": ["portrait", "content"]},
    "comparison": {"type": "columns", "ratios": [1, 1], "names": ["left", "right"]},
    "pip-corner": {"type": "columns", "ratios": [3, 1], "names": ["main", "pip"]},
}


def get_preset(name: str, **layout_kwargs) -> Union[Slot, List[Slot], List[List[Slot]]]:
    """
    Get a preset layout by name.

    Args:
        name: Preset name (see LAYOUT_PRESETS)
        **layout_kwargs: Override Layout parameters (width, height, margin, etc.)

    Returns:
        Slot(s) for the preset layout

    Example:
        left, right = get_preset("split-1-2")
        grid = get_preset("grid-2x2", margin=50)
    """
    if name not in LAYOUT_PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(LAYOUT_PRESETS.keys())}")

    schema = LAYOUT_PRESETS[name]
    layout = Layout(**layout_kwargs)
    return layout.from_schema(schema)


# =============================================================================
# EXPORT UTILITIES
# =============================================================================

def slots_to_json(slots: Union[Slot, List[Slot], List[List[Slot]]]) -> str:
    """
    Export slots to JSON string.

    Useful for passing to other renderers (Motion Canvas, Remotion).
    """
    if isinstance(slots, Slot):
        return json.dumps(slots.to_dict(), indent=2)
    elif isinstance(slots, list) and slots and isinstance(slots[0], Slot):
        return json.dumps([s.to_dict() for s in slots], indent=2)
    elif isinstance(slots, list) and slots and isinstance(slots[0], list):
        return json.dumps([[s.to_dict() for s in row] for row in slots], indent=2)
    else:
        raise ValueError("Invalid slots format")


def slots_from_json(json_str: str) -> Union[Slot, List[Slot], List[List[Slot]]]:
    """
    Import slots from JSON string.
    """
    data = json.loads(json_str)

    if isinstance(data, dict):
        return Slot.from_dict(data)
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        return [Slot.from_dict(s) for s in data]
    elif isinstance(data, list) and data and isinstance(data[0], list):
        return [[Slot.from_dict(s) for s in row] for row in data]
    else:
        raise ValueError("Invalid JSON format")
