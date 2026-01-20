"""
Lottie animation utilities for NOLAN.

This module provides functions for customizing Lottie animations,
including text replacement, color transformation, and timing adjustments.
"""

import json
import re
from pathlib import Path
from typing import Any


def hex_to_lottie_rgb(hex_color: str) -> list[float]:
    """
    Convert hex color to Lottie RGB format (0-1 range).

    Args:
        hex_color: Hex color string (e.g., '#FF5500' or 'FF5500')

    Returns:
        List of [r, g, b] values in 0-1 range
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")

    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return [round(r, 3), round(g, 3), round(b, 3)]


def lottie_rgb_to_hex(rgb: list[float]) -> str:
    """
    Convert Lottie RGB (0-1 range) to hex color.

    Args:
        rgb: List of [r, g, b] values in 0-1 range

    Returns:
        Hex color string (e.g., '#FF5500')
    """
    r = int(min(1, max(0, rgb[0])) * 255)
    g = int(min(1, max(0, rgb[1])) * 255)
    b = int(min(1, max(0, rgb[2])) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def validate_lottie(data: dict) -> tuple[bool, str | None]:
    """
    Validate that a dictionary is a valid Lottie animation.

    Args:
        data: Dictionary to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Core required fields (v is optional - some files omit it)
    required_fields = ['fr', 'ip', 'op', 'w', 'h', 'layers']

    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    if not isinstance(data['layers'], list):
        return False, "layers must be a list"

    if not isinstance(data['fr'], (int, float)) or data['fr'] <= 0:
        return False, "fr (frame rate) must be a positive number"

    if not isinstance(data['w'], (int, float)) or data['w'] <= 0:
        return False, "w (width) must be a positive number"

    if not isinstance(data['h'], (int, float)) or data['h'] <= 0:
        return False, "h (height) must be a positive number"

    return True, None


def load_lottie(path: str | Path) -> dict:
    """
    Load and validate a Lottie JSON file.

    Args:
        path: Path to the Lottie JSON file

    Returns:
        Lottie data dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not valid Lottie JSON
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Lottie file not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    is_valid, error = validate_lottie(data)
    if not is_valid:
        raise ValueError(f"Invalid Lottie file: {error}")

    return data


def save_lottie(data: dict, path: str | Path) -> None:
    """
    Save Lottie data to a JSON file.

    Args:
        data: Lottie data dictionary
        path: Output path
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))


def get_text_layers(data: dict) -> list[dict]:
    """
    Extract all text layers from a Lottie animation.

    Args:
        data: Lottie data dictionary

    Returns:
        List of text layer dictionaries with 'name', 'text', and 'path' keys
    """
    text_layers = []

    def find_text_layers(layers: list, path_prefix: str = ""):
        for i, layer in enumerate(layers):
            layer_path = f"{path_prefix}layers[{i}]"

            # Text layer type is 5
            if layer.get('ty') == 5:
                text_data = layer.get('t', {}).get('d', {}).get('k', [])
                if text_data and isinstance(text_data, list) and len(text_data) > 0:
                    text_content = text_data[0].get('s', {}).get('t', '')
                    text_layers.append({
                        'name': layer.get('nm', f'Text Layer {i}'),
                        'text': text_content,
                        'path': layer_path,
                        'layer': layer
                    })

            # Check precomp layers
            if layer.get('ty') == 0 and 'refId' in layer:
                ref_id = layer['refId']
                assets = data.get('assets', [])
                for asset in assets:
                    if asset.get('id') == ref_id and 'layers' in asset:
                        find_text_layers(asset['layers'], f"assets[{ref_id}].")

    find_text_layers(data.get('layers', []))
    return text_layers


def replace_text(data: dict, old_text: str, new_text: str) -> int:
    """
    Replace text content in all text layers.

    Args:
        data: Lottie data dictionary (modified in place)
        old_text: Text to find
        new_text: Replacement text

    Returns:
        Number of replacements made
    """
    count = 0

    def process_layers(layers: list):
        nonlocal count
        for layer in layers:
            if layer.get('ty') == 5:  # Text layer
                text_data = layer.get('t', {}).get('d', {}).get('k', [])
                for keyframe in text_data:
                    if 's' in keyframe and 't' in keyframe['s']:
                        if keyframe['s']['t'] == old_text:
                            keyframe['s']['t'] = new_text
                            count += 1

            # Check precomp layers
            if layer.get('ty') == 0 and 'refId' in layer:
                ref_id = layer['refId']
                assets = data.get('assets', [])
                for asset in assets:
                    if asset.get('id') == ref_id and 'layers' in asset:
                        process_layers(asset['layers'])

    process_layers(data.get('layers', []))
    return count


def transform_colors(
    data: dict,
    transform_fn: callable = None,
    color_map: dict[str, str] = None
) -> int:
    """
    Transform colors in a Lottie animation.

    Args:
        data: Lottie data dictionary (modified in place)
        transform_fn: Function that takes [r, g, b] and returns new [r, g, b]
        color_map: Dict mapping hex colors to new hex colors (e.g., {'#ff0000': '#00ff00'})

    Returns:
        Number of colors transformed
    """
    count = 0

    # Build color lookup if color_map provided
    color_lookup = {}
    if color_map:
        for old_hex, new_hex in color_map.items():
            old_rgb = hex_to_lottie_rgb(old_hex)
            new_rgb = hex_to_lottie_rgb(new_hex)
            # Use rounded key for matching
            key = tuple(round(v, 2) for v in old_rgb)
            color_lookup[key] = new_rgb

    def process_value(obj: Any, depth: int = 0) -> None:
        nonlocal count
        if depth > 50:  # Prevent infinite recursion
            return

        if isinstance(obj, dict):
            # Check for color arrays in 'k' or 'c' keys
            for key in ['k', 'c']:
                if key in obj:
                    val = obj[key]
                    if isinstance(val, list) and len(val) in [3, 4]:
                        # Check if it looks like a color (all values 0-1)
                        if all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in val[:3]):
                            rgb = val[:3]
                            new_rgb = None

                            # Try color map first
                            if color_lookup:
                                lookup_key = tuple(round(v, 2) for v in rgb)
                                if lookup_key in color_lookup:
                                    new_rgb = color_lookup[lookup_key]

                            # Then try transform function
                            if new_rgb is None and transform_fn:
                                new_rgb = transform_fn(rgb)

                            if new_rgb and new_rgb != rgb:
                                if len(val) == 4:
                                    obj[key] = [new_rgb[0], new_rgb[1], new_rgb[2], val[3]]
                                else:
                                    obj[key] = new_rgb
                                count += 1

            # Recurse into all dict values
            for v in obj.values():
                process_value(v, depth + 1)

        elif isinstance(obj, list):
            for item in obj:
                process_value(item, depth + 1)

    process_value(data)
    return count


def set_duration(data: dict, frames: int = None, seconds: float = None) -> None:
    """
    Set the duration of a Lottie animation.

    Args:
        data: Lottie data dictionary (modified in place)
        frames: Duration in frames (mutually exclusive with seconds)
        seconds: Duration in seconds (mutually exclusive with frames)
    """
    if frames is not None and seconds is not None:
        raise ValueError("Specify either frames or seconds, not both")

    if seconds is not None:
        fps = data.get('fr', 30)
        frames = int(seconds * fps)

    if frames is not None:
        data['op'] = frames


def set_fps(data: dict, fps: int | float) -> None:
    """
    Set the frame rate of a Lottie animation.

    Args:
        data: Lottie data dictionary (modified in place)
        fps: New frame rate
    """
    if fps <= 0:
        raise ValueError("FPS must be positive")
    data['fr'] = fps


def set_dimensions(data: dict, width: int = None, height: int = None) -> None:
    """
    Set the dimensions of a Lottie animation.

    Args:
        data: Lottie data dictionary (modified in place)
        width: New width in pixels
        height: New height in pixels
    """
    if width is not None:
        if width <= 0:
            raise ValueError("Width must be positive")
        data['w'] = width

    if height is not None:
        if height <= 0:
            raise ValueError("Height must be positive")
        data['h'] = height


def customize_lottie(
    input_path: str | Path,
    output_path: str | Path,
    text_replacements: dict[str, str] = None,
    color_map: dict[str, str] = None,
    color_transform: callable = None,
    duration_frames: int = None,
    duration_seconds: float = None,
    fps: int | float = None,
    width: int = None,
    height: int = None
) -> dict:
    """
    Customize a Lottie animation file with various modifications.

    This is the main entry point for Lottie customization, combining
    multiple modification operations into a single call.

    Args:
        input_path: Path to input Lottie JSON file
        output_path: Path to save modified Lottie JSON
        text_replacements: Dict mapping old text to new text
        color_map: Dict mapping hex colors to new hex colors
        color_transform: Function to transform colors
        duration_frames: New duration in frames
        duration_seconds: New duration in seconds
        fps: New frame rate
        width: New width in pixels
        height: New height in pixels

    Returns:
        The modified Lottie data dictionary

    Example:
        >>> customize_lottie(
        ...     'input.json',
        ...     'output.json',
        ...     text_replacements={'Hello': 'World'},
        ...     color_map={'#ff0000': '#00ff00'},
        ...     fps=60,
        ...     duration_seconds=5
        ... )
    """
    data = load_lottie(input_path)

    # Apply text replacements
    if text_replacements:
        for old_text, new_text in text_replacements.items():
            replace_text(data, old_text, new_text)

    # Apply color transformations
    if color_map or color_transform:
        transform_colors(data, transform_fn=color_transform, color_map=color_map)

    # Set timing
    if duration_frames is not None or duration_seconds is not None:
        set_duration(data, frames=duration_frames, seconds=duration_seconds)

    if fps is not None:
        set_fps(data, fps)

    # Set dimensions
    if width is not None or height is not None:
        set_dimensions(data, width=width, height=height)

    # Save output
    save_lottie(data, output_path)

    return data


def get_lottie_info(path: str | Path) -> dict:
    """
    Get information about a Lottie animation file.

    Args:
        path: Path to Lottie JSON file

    Returns:
        Dictionary with animation metadata
    """
    data = load_lottie(path)

    fps = data.get('fr', 30)
    ip = data.get('ip', 0)
    op = data.get('op', 0)
    total_frames = op - ip
    duration_seconds = total_frames / fps if fps > 0 else 0

    text_layers = get_text_layers(data)

    return {
        'version': data.get('v', 'unknown'),
        'name': data.get('nm', 'Untitled'),
        'width': data.get('w', 0),
        'height': data.get('h', 0),
        'fps': fps,
        'in_point': ip,
        'out_point': op,
        'total_frames': total_frames,
        'duration_seconds': round(duration_seconds, 2),
        'layer_count': len(data.get('layers', [])),
        'asset_count': len(data.get('assets', [])),
        'text_layers': [
            {'name': t['name'], 'text': t['text']}
            for t in text_layers
        ]
    }


# Preset color transforms
def cyberpunk_transform(rgb: list[float]) -> list[float]:
    """Transform colors to cyberpunk palette (cyan/magenta/purple)."""
    r, g, b = rgb
    new_r = min(1, r * 0.5 + g * 0.3 + 0.2)
    new_g = min(1, g * 0.3 + b * 0.5)
    new_b = min(1, b * 0.8 + r * 0.2 + 0.1)
    return [round(new_r, 3), round(new_g, 3), round(new_b, 3)]


def noir_transform(rgb: list[float]) -> list[float]:
    """Transform colors to noir palette (grayscale with slight warmth)."""
    r, g, b = rgb
    gray = r * 0.299 + g * 0.587 + b * 0.114
    # Add slight sepia
    new_r = min(1, gray * 1.1)
    new_g = min(1, gray * 1.0)
    new_b = min(1, gray * 0.9)
    return [round(new_r, 3), round(new_g, 3), round(new_b, 3)]


def invert_transform(rgb: list[float]) -> list[float]:
    """Invert colors."""
    return [round(1 - rgb[0], 3), round(1 - rgb[1], 3), round(1 - rgb[2], 3)]


# =============================================================================
# Template Schema System
# =============================================================================

def analyze_lottie(path: str | Path) -> dict:
    """
    Analyze a Lottie file and discover all customizable fields.

    Returns a dictionary with:
    - text_fields: Text layers with their paths and current values
    - color_fields: Fill/stroke colors with paths and hex values
    - timing: FPS, duration, frame range
    - dimensions: Width and height

    Args:
        path: Path to Lottie JSON file

    Returns:
        Analysis dictionary with all customizable fields
    """
    data = load_lottie(path)

    analysis = {
        "text_fields": [],
        "color_fields": [],
        "timing": {
            "fps": data.get("fr", 30),
            "in_point": data.get("ip", 0),
            "out_point": data.get("op", 0),
            "duration_frames": data.get("op", 0) - data.get("ip", 0),
            "duration_seconds": round(
                (data.get("op", 0) - data.get("ip", 0)) / data.get("fr", 30), 2
            )
        },
        "dimensions": {
            "width": data.get("w", 0),
            "height": data.get("h", 0)
        }
    }

    # Find text fields
    _find_text_fields(data, data.get("layers", []), "layers", analysis["text_fields"])

    # Find color fields
    _find_color_fields(data, data.get("layers", []), "layers", analysis["color_fields"])

    return analysis


def _find_text_fields(
    root_data: dict,
    layers: list,
    path_prefix: str,
    results: list
) -> None:
    """Recursively find text layers in Lottie data."""
    for i, layer in enumerate(layers):
        layer_path = f"{path_prefix}[{i}]"
        layer_name = layer.get("nm", f"Layer {i}")

        # Text layer (ty=5)
        if layer.get("ty") == 5:
            text_data = layer.get("t", {}).get("d", {}).get("k", [])
            if text_data and isinstance(text_data, list) and len(text_data) > 0:
                text_props = text_data[0].get("s", {})
                text_content = text_props.get("t", "")

                field = {
                    "name": layer_name,
                    "path": f"{layer_path}.t.d.k[0].s.t",
                    "current_value": text_content,
                    "type": "text",
                    "properties": {}
                }

                # Extract text properties
                if "f" in text_props:
                    field["properties"]["font"] = text_props["f"]
                if "s" in text_props:
                    field["properties"]["size"] = text_props["s"]
                if "fc" in text_props:
                    field["properties"]["color"] = lottie_rgb_to_hex(text_props["fc"][:3])
                if "j" in text_props:
                    field["properties"]["justify"] = {0: "left", 1: "right", 2: "center"}.get(
                        text_props["j"], "left"
                    )

                results.append(field)

        # Precomp layer (ty=0) - recurse into assets
        if layer.get("ty") == 0 and "refId" in layer:
            ref_id = layer["refId"]
            for asset in root_data.get("assets", []):
                if asset.get("id") == ref_id and "layers" in asset:
                    _find_text_fields(
                        root_data,
                        asset["layers"],
                        f"assets[{ref_id}].layers",
                        results
                    )


def _find_color_fields(
    root_data: dict,
    layers: list,
    path_prefix: str,
    results: list,
    seen_colors: set = None
) -> None:
    """Recursively find color fields in Lottie data."""
    if seen_colors is None:
        seen_colors = set()

    for i, layer in enumerate(layers):
        layer_path = f"{path_prefix}[{i}]"
        layer_name = layer.get("nm", f"Layer {i}")

        # Process shapes
        shapes = layer.get("shapes", [])
        _find_colors_in_shapes(shapes, f"{layer_path}.shapes", layer_name, results, seen_colors)

        # Precomp layer - recurse into assets
        if layer.get("ty") == 0 and "refId" in layer:
            ref_id = layer["refId"]
            for asset in root_data.get("assets", []):
                if asset.get("id") == ref_id and "layers" in asset:
                    _find_color_fields(
                        root_data,
                        asset["layers"],
                        f"assets[{ref_id}].layers",
                        results,
                        seen_colors
                    )


def _find_colors_in_shapes(
    shapes: list,
    path_prefix: str,
    layer_name: str,
    results: list,
    seen_colors: set
) -> None:
    """Find colors in shape layers."""
    for i, shape in enumerate(shapes):
        shape_path = f"{path_prefix}[{i}]"
        shape_type = shape.get("ty", "")
        shape_name = shape.get("nm", f"Shape {i}")

        # Fill (fl)
        if shape_type == "fl":
            color_data = shape.get("c", {})
            color_val = color_data.get("k", [])
            if isinstance(color_val, list) and len(color_val) >= 3:
                # Check if it's static color (not animated)
                if all(isinstance(v, (int, float)) for v in color_val[:3]):
                    hex_color = lottie_rgb_to_hex(color_val[:3])
                    color_key = f"fill:{hex_color}"
                    if color_key not in seen_colors:
                        seen_colors.add(color_key)
                        results.append({
                            "name": f"{layer_name} / {shape_name}",
                            "path": f"{shape_path}.c.k",
                            "current_value": hex_color,
                            "type": "fill"
                        })

        # Stroke (st)
        elif shape_type == "st":
            color_data = shape.get("c", {})
            color_val = color_data.get("k", [])
            if isinstance(color_val, list) and len(color_val) >= 3:
                if all(isinstance(v, (int, float)) for v in color_val[:3]):
                    hex_color = lottie_rgb_to_hex(color_val[:3])
                    color_key = f"stroke:{hex_color}"
                    if color_key not in seen_colors:
                        seen_colors.add(color_key)
                        results.append({
                            "name": f"{layer_name} / {shape_name}",
                            "path": f"{shape_path}.c.k",
                            "current_value": hex_color,
                            "type": "stroke"
                        })

        # Group (gr) - recurse into items
        elif shape_type == "gr":
            items = shape.get("it", [])
            _find_colors_in_shapes(items, f"{shape_path}.it", layer_name, results, seen_colors)


def generate_schema(path: str | Path, template_name: str = None) -> dict:
    """
    Generate a starter schema file from Lottie analysis.

    The generated schema has placeholder field names that should be
    manually curated to semantic names.

    Args:
        path: Path to Lottie JSON file
        template_name: Optional name for the template

    Returns:
        Schema dictionary ready to be saved
    """
    analysis = analyze_lottie(path)
    path = Path(path)

    schema = {
        "$schema": "lottie-template-schema-v1",
        "name": template_name or path.stem,
        "description": "TODO: Add description",
        "usage": "TODO: Add usage examples",
        "fields": {},
        "timing": analysis["timing"],
        "dimensions": analysis["dimensions"]
    }

    # Add text fields with placeholder names
    for i, field in enumerate(analysis["text_fields"]):
        field_key = f"text_{i + 1}"
        schema["fields"][field_key] = {
            "type": "text",
            "label": field["name"],
            "path": field["path"],
            "default": field["current_value"],
            "properties": field.get("properties", {})
        }

    # Add color fields
    for i, field in enumerate(analysis["color_fields"]):
        field_key = f"color_{i + 1}"
        schema["fields"][field_key] = {
            "type": "color",
            "label": field["name"],
            "path": field["path"],
            "default": field["current_value"],
            "color_type": field["type"]  # fill or stroke
        }

    return schema


def load_schema(template_path: str | Path) -> dict | None:
    """
    Load the schema for a Lottie template.

    Looks for {template_name}.schema.json alongside the template file.

    Args:
        template_path: Path to Lottie JSON file

    Returns:
        Schema dictionary or None if no schema exists
    """
    template_path = Path(template_path)
    schema_path = template_path.with_suffix(".schema.json")

    if not schema_path.exists():
        return None

    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_schema(schema: dict, template_path: str | Path) -> Path:
    """
    Save a schema file alongside a Lottie template.

    Args:
        schema: Schema dictionary
        template_path: Path to the Lottie JSON file

    Returns:
        Path to the saved schema file
    """
    template_path = Path(template_path)
    schema_path = template_path.with_suffix(".schema.json")

    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    return schema_path


def render_template(
    template_path: str | Path,
    output_path: str | Path = None,
    **field_values
) -> dict:
    """
    Render a Lottie template with field values from its schema.

    This is the main "magicbox" API - pass semantic field names and get
    a customized Lottie animation.

    Args:
        template_path: Path to Lottie JSON file
        output_path: Path to save rendered animation (optional)
        **field_values: Field values matching schema field names

    Returns:
        The rendered Lottie data dictionary

    Raises:
        ValueError: If template has no schema or field name is invalid

    Example:
        >>> render_template(
        ...     "assets/common/lottie/lower-thirds/simple.json",
        ...     "output/speaker.json",
        ...     name="Jane Doe",
        ...     title="CEO, TechCorp",
        ...     accent_color="#FFD700"
        ... )
    """
    template_path = Path(template_path)

    # Load schema
    schema = load_schema(template_path)
    if schema is None:
        raise ValueError(
            f"No schema found for {template_path}. "
            f"Create {template_path.with_suffix('.schema.json')} first."
        )

    # Load template
    data = load_lottie(template_path)

    # Apply field values
    for field_name, value in field_values.items():
        if field_name not in schema["fields"]:
            available = list(schema["fields"].keys())
            raise ValueError(
                f"Unknown field '{field_name}'. Available fields: {available}"
            )

        field_def = schema["fields"][field_name]
        field_path = field_def["path"]
        field_type = field_def["type"]

        if field_type == "text":
            _set_value_at_path(data, field_path, value)
        elif field_type == "color":
            # Convert hex to Lottie RGB
            rgb = hex_to_lottie_rgb(value)
            # Add alpha if needed
            current = _get_value_at_path(data, field_path)
            if isinstance(current, list) and len(current) == 4:
                rgb.append(current[3])  # Preserve alpha
            _set_value_at_path(data, field_path, rgb)

    # Save if output path provided
    if output_path:
        save_lottie(data, output_path)

    return data


def _get_value_at_path(data: dict, path: str) -> Any:
    """Get a value from nested dict/list using path notation."""
    current = data

    # Parse path like "layers[0].shapes[1].c.k"
    parts = re.split(r'\.|\[', path)

    for part in parts:
        part = part.rstrip(']')
        if not part:
            continue

        if part.isdigit():
            current = current[int(part)]
        else:
            current = current[part]

    return current


def _set_value_at_path(data: dict, path: str, value: Any) -> None:
    """Set a value in nested dict/list using path notation."""
    parts = re.split(r'\.|\[', path)
    parts = [p.rstrip(']') for p in parts if p]

    current = data
    for part in parts[:-1]:
        if part.isdigit():
            current = current[int(part)]
        else:
            current = current[part]

    final_key = parts[-1]
    if final_key.isdigit():
        current[int(final_key)] = value
    else:
        current[final_key] = value


def list_templates(
    lottie_dir: str | Path = "assets/common/lottie"
) -> list[dict]:
    """
    List all Lottie templates with their schema status.

    Args:
        lottie_dir: Base directory for Lottie templates

    Returns:
        List of template info dictionaries
    """
    lottie_dir = Path(lottie_dir)
    templates = []

    for json_file in lottie_dir.rglob("*.json"):
        # Skip catalog, schema, and meta files
        if json_file.name in ("catalog.json",):
            continue
        if ".schema." in json_file.name or ".meta." in json_file.name:
            continue

        schema_path = json_file.with_suffix(".schema.json")
        schema = load_schema(json_file) if schema_path.exists() else None

        rel_path = json_file.relative_to(lottie_dir)

        templates.append({
            "path": str(rel_path),
            "category": rel_path.parent.name if rel_path.parent.name != "." else "root",
            "name": schema["name"] if schema else json_file.stem,
            "has_schema": schema is not None,
            "fields": list(schema["fields"].keys()) if schema else [],
            "description": schema.get("description", "") if schema else ""
        })

    return templates
