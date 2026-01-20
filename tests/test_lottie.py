"""Tests for the Lottie animation utilities and schema system."""

import pytest
from pathlib import Path
import tempfile
import shutil
import json

from nolan.lottie import (
    # Color utilities
    hex_to_lottie_rgb,
    lottie_rgb_to_hex,
    # Lottie file operations
    validate_lottie,
    load_lottie,
    save_lottie,
    get_lottie_info,
    # Text and color operations
    get_text_layers,
    replace_text,
    transform_colors,
    # Timing and dimensions
    set_duration,
    set_fps,
    set_dimensions,
    # Main customization API
    customize_lottie,
    # Color transforms
    noir_transform,
    invert_transform,
    # Schema system
    analyze_lottie,
    generate_schema,
    load_schema,
    save_schema,
    render_template,
    list_templates,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_lottie():
    """Create a minimal valid Lottie animation."""
    return {
        "v": "5.5.0",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 1920,
        "h": 1080,
        "nm": "Test Animation",
        "layers": []
    }


@pytest.fixture
def lottie_with_text():
    """Create a Lottie animation with text layers."""
    return {
        "v": "5.5.0",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 1920,
        "h": 1080,
        "nm": "Text Animation",
        "layers": [
            {
                "ty": 5,  # Text layer
                "nm": "Title",
                "t": {
                    "d": {
                        "k": [{
                            "s": {
                                "t": "Hello World",
                                "f": "Arial",
                                "s": 48,
                                "fc": [1, 1, 1],
                                "j": 2
                            },
                            "t": 0
                        }]
                    }
                }
            },
            {
                "ty": 5,
                "nm": "Subtitle",
                "t": {
                    "d": {
                        "k": [{
                            "s": {
                                "t": "Welcome",
                                "f": "Arial",
                                "s": 24,
                                "fc": [0.5, 0.5, 0.5],
                                "j": 2
                            },
                            "t": 0
                        }]
                    }
                }
            }
        ],
        "assets": []
    }


@pytest.fixture
def lottie_with_shapes():
    """Create a Lottie animation with shape layers and colors."""
    return {
        "v": "5.5.0",
        "fr": 30,
        "ip": 0,
        "op": 60,
        "w": 1920,
        "h": 1080,
        "nm": "Shape Animation",
        "layers": [
            {
                "ty": 4,  # Shape layer
                "nm": "Rectangle",
                "shapes": [
                    {
                        "ty": "gr",
                        "nm": "Group",
                        "it": [
                            {
                                "ty": "rc",
                                "nm": "Rectangle Path"
                            },
                            {
                                "ty": "fl",
                                "nm": "Fill",
                                "c": {"k": [1, 0, 0, 1]}  # Red
                            },
                            {
                                "ty": "st",
                                "nm": "Stroke",
                                "c": {"k": [0, 0, 1, 1]}  # Blue
                            }
                        ]
                    }
                ]
            }
        ],
        "assets": []
    }


@pytest.fixture
def temp_lottie_dir():
    """Create a temporary directory with Lottie files and schemas."""
    temp_dir = tempfile.mkdtemp()
    lottie_dir = Path(temp_dir) / "lottie"
    lottie_dir.mkdir()

    # Create a test category
    test_category = lottie_dir / "test-category"
    test_category.mkdir()

    # Create a test Lottie file
    test_lottie = {
        "v": "5.5.0",
        "fr": 30,
        "ip": 0,
        "op": 90,
        "w": 800,
        "h": 600,
        "nm": "Test Template",
        "layers": [
            {
                "ty": 5,
                "nm": "Message",
                "t": {
                    "d": {
                        "k": [{
                            "s": {
                                "t": "Default Text",
                                "f": "Arial",
                                "s": 32,
                                "fc": [1, 1, 1],
                                "j": 2
                            },
                            "t": 0
                        }]
                    }
                }
            },
            {
                "ty": 4,
                "nm": "Background",
                "shapes": [
                    {
                        "ty": "gr",
                        "nm": "BG",
                        "it": [
                            {"ty": "rc", "nm": "Rect"},
                            {"ty": "fl", "nm": "Fill", "c": {"k": [0.2, 0.4, 0.8, 1]}}
                        ]
                    }
                ]
            }
        ],
        "assets": []
    }

    lottie_path = test_category / "test-template.json"
    with open(lottie_path, "w") as f:
        json.dump(test_lottie, f)

    # Create a schema for it
    schema = {
        "$schema": "lottie-template-schema-v1",
        "name": "Test Template",
        "description": "A test template for unit testing.",
        "usage": "Testing purposes only.",
        "fields": {
            "message": {
                "type": "text",
                "label": "Message",
                "path": "layers[0].t.d.k[0].s.t",
                "default": "Default Text"
            },
            "bg_color": {
                "type": "color",
                "label": "Background Color",
                "path": "layers[1].shapes[0].it[1].c.k",
                "default": "#3366cc",
                "color_type": "fill"
            }
        },
        "timing": {"fps": 30, "duration_seconds": 3.0},
        "dimensions": {"width": 800, "height": 600}
    }

    schema_path = test_category / "test-template.schema.json"
    with open(schema_path, "w") as f:
        json.dump(schema, f)

    yield lottie_dir

    # Cleanup
    shutil.rmtree(temp_dir)


# =============================================================================
# Color Utilities Tests
# =============================================================================

class TestColorUtilities:
    """Tests for color conversion functions."""

    def test_hex_to_lottie_rgb_basic(self):
        """Convert basic hex colors."""
        assert hex_to_lottie_rgb("#FF0000") == [1.0, 0.0, 0.0]
        assert hex_to_lottie_rgb("#00FF00") == [0.0, 1.0, 0.0]
        assert hex_to_lottie_rgb("#0000FF") == [0.0, 0.0, 1.0]

    def test_hex_to_lottie_rgb_without_hash(self):
        """Convert hex without # prefix."""
        assert hex_to_lottie_rgb("FF0000") == [1.0, 0.0, 0.0]

    def test_hex_to_lottie_rgb_mixed(self):
        """Convert mixed hex colors."""
        rgb = hex_to_lottie_rgb("#3366CC")
        assert rgb[0] == pytest.approx(0.2, abs=0.01)
        assert rgb[1] == pytest.approx(0.4, abs=0.01)
        assert rgb[2] == pytest.approx(0.8, abs=0.01)

    def test_hex_to_lottie_rgb_invalid(self):
        """Invalid hex raises ValueError."""
        with pytest.raises(ValueError):
            hex_to_lottie_rgb("#FFF")  # Too short
        with pytest.raises(ValueError):
            hex_to_lottie_rgb("#GGGGGG")  # Invalid chars

    def test_lottie_rgb_to_hex_basic(self):
        """Convert Lottie RGB to hex."""
        assert lottie_rgb_to_hex([1.0, 0.0, 0.0]) == "#ff0000"
        assert lottie_rgb_to_hex([0.0, 1.0, 0.0]) == "#00ff00"
        assert lottie_rgb_to_hex([0.0, 0.0, 1.0]) == "#0000ff"

    def test_lottie_rgb_to_hex_clamped(self):
        """Values outside 0-1 are clamped."""
        assert lottie_rgb_to_hex([1.5, -0.5, 0.5]) == "#ff007f"

    def test_roundtrip_conversion(self):
        """Hex -> RGB -> Hex preserves value."""
        original = "#3366CC"
        rgb = hex_to_lottie_rgb(original)
        result = lottie_rgb_to_hex(rgb)
        assert result.lower() == original.lower()


# =============================================================================
# Validation Tests
# =============================================================================

class TestValidation:
    """Tests for Lottie validation."""

    def test_validate_valid_lottie(self, sample_lottie):
        """Valid Lottie passes validation."""
        is_valid, error = validate_lottie(sample_lottie)
        assert is_valid is True
        assert error is None

    def test_validate_missing_field(self, sample_lottie):
        """Missing required field fails validation."""
        del sample_lottie["fr"]
        is_valid, error = validate_lottie(sample_lottie)
        assert is_valid is False
        assert "fr" in error

    def test_validate_invalid_fps(self, sample_lottie):
        """Invalid FPS fails validation."""
        sample_lottie["fr"] = -30
        is_valid, error = validate_lottie(sample_lottie)
        assert is_valid is False
        assert "fr" in error

    def test_validate_invalid_dimensions(self, sample_lottie):
        """Invalid dimensions fail validation."""
        sample_lottie["w"] = 0
        is_valid, error = validate_lottie(sample_lottie)
        assert is_valid is False
        assert "w" in error


# =============================================================================
# File Operations Tests
# =============================================================================

class TestFileOperations:
    """Tests for loading and saving Lottie files."""

    def test_load_and_save(self, sample_lottie):
        """Load and save preserves data."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(sample_lottie, temp_path)
            loaded = load_lottie(temp_path)

            assert loaded["fr"] == sample_lottie["fr"]
            assert loaded["w"] == sample_lottie["w"]
            assert loaded["nm"] == sample_lottie["nm"]
        finally:
            Path(temp_path).unlink()

    def test_load_nonexistent_raises(self):
        """Loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_lottie("/nonexistent/path.json")

    def test_get_lottie_info(self, sample_lottie):
        """get_lottie_info extracts metadata."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(sample_lottie, temp_path)
            info = get_lottie_info(temp_path)

            assert info["fps"] == 30
            assert info["width"] == 1920
            assert info["height"] == 1080
            assert info["total_frames"] == 60
            assert info["duration_seconds"] == 2.0
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Text Operations Tests
# =============================================================================

class TestTextOperations:
    """Tests for text layer operations."""

    def test_get_text_layers(self, lottie_with_text):
        """Extract text layers from animation."""
        layers = get_text_layers(lottie_with_text)

        assert len(layers) == 2
        assert layers[0]["name"] == "Title"
        assert layers[0]["text"] == "Hello World"
        assert layers[1]["name"] == "Subtitle"
        assert layers[1]["text"] == "Welcome"

    def test_replace_text(self, lottie_with_text):
        """Replace text in layers."""
        count = replace_text(lottie_with_text, "Hello World", "Goodbye World")

        assert count == 1
        layers = get_text_layers(lottie_with_text)
        assert layers[0]["text"] == "Goodbye World"

    def test_replace_text_no_match(self, lottie_with_text):
        """Replace returns 0 when no match."""
        count = replace_text(lottie_with_text, "Nonexistent", "Replacement")
        assert count == 0


# =============================================================================
# Color Operations Tests
# =============================================================================

class TestColorOperations:
    """Tests for color transformation."""

    def test_transform_colors_with_map(self, lottie_with_shapes):
        """Transform colors using color map."""
        # Change red fill to green
        count = transform_colors(
            lottie_with_shapes,
            color_map={"#FF0000": "#00FF00"}
        )

        assert count >= 1
        fill = lottie_with_shapes["layers"][0]["shapes"][0]["it"][1]
        assert fill["c"]["k"][:3] == [0.0, 1.0, 0.0]

    def test_transform_colors_with_function(self, lottie_with_shapes):
        """Transform colors using function."""
        count = transform_colors(
            lottie_with_shapes,
            transform_fn=invert_transform
        )

        assert count >= 1

    def test_noir_transform(self):
        """Noir transform creates grayscale with warmth."""
        rgb = noir_transform([1, 0, 0])  # Red
        # Should be grayish with slight warm tint
        assert rgb[0] > rgb[2]  # More red than blue


# =============================================================================
# Timing and Dimensions Tests
# =============================================================================

class TestTimingAndDimensions:
    """Tests for timing and dimension modifications."""

    def test_set_duration_frames(self, sample_lottie):
        """Set duration by frames."""
        set_duration(sample_lottie, frames=120)
        assert sample_lottie["op"] == 120

    def test_set_duration_seconds(self, sample_lottie):
        """Set duration by seconds."""
        set_duration(sample_lottie, seconds=5)
        assert sample_lottie["op"] == 150  # 5 * 30fps

    def test_set_duration_mutually_exclusive(self, sample_lottie):
        """Can't specify both frames and seconds."""
        with pytest.raises(ValueError):
            set_duration(sample_lottie, frames=60, seconds=2)

    def test_set_fps(self, sample_lottie):
        """Set frame rate."""
        set_fps(sample_lottie, 60)
        assert sample_lottie["fr"] == 60

    def test_set_fps_invalid(self, sample_lottie):
        """Invalid FPS raises ValueError."""
        with pytest.raises(ValueError):
            set_fps(sample_lottie, 0)

    def test_set_dimensions(self, sample_lottie):
        """Set dimensions."""
        set_dimensions(sample_lottie, width=3840, height=2160)
        assert sample_lottie["w"] == 3840
        assert sample_lottie["h"] == 2160


# =============================================================================
# Schema System Tests
# =============================================================================

class TestAnalyzeLottie:
    """Tests for Lottie analysis."""

    def test_analyze_text_fields(self, lottie_with_text):
        """Analyze finds text fields."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(lottie_with_text, temp_path)
            analysis = analyze_lottie(temp_path)

            assert len(analysis["text_fields"]) == 2
            assert analysis["text_fields"][0]["current_value"] == "Hello World"
            assert analysis["text_fields"][0]["type"] == "text"
        finally:
            Path(temp_path).unlink()

    def test_analyze_color_fields(self, lottie_with_shapes):
        """Analyze finds color fields."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(lottie_with_shapes, temp_path)
            analysis = analyze_lottie(temp_path)

            assert len(analysis["color_fields"]) >= 2
            # Should find fill and stroke
            types = {f["type"] for f in analysis["color_fields"]}
            assert "fill" in types
            assert "stroke" in types
        finally:
            Path(temp_path).unlink()

    def test_analyze_timing(self, sample_lottie):
        """Analyze extracts timing info."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(sample_lottie, temp_path)
            analysis = analyze_lottie(temp_path)

            assert analysis["timing"]["fps"] == 30
            assert analysis["timing"]["duration_frames"] == 60
            assert analysis["timing"]["duration_seconds"] == 2.0
        finally:
            Path(temp_path).unlink()


class TestSchemaOperations:
    """Tests for schema generation and loading."""

    def test_generate_schema(self, lottie_with_text):
        """Generate schema from Lottie file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(lottie_with_text, temp_path)
            schema = generate_schema(temp_path, template_name="Test")

            assert schema["$schema"] == "lottie-template-schema-v1"
            assert schema["name"] == "Test"
            assert "text_1" in schema["fields"]
            assert schema["fields"]["text_1"]["type"] == "text"
        finally:
            Path(temp_path).unlink()

    def test_save_and_load_schema(self, temp_lottie_dir):
        """Save and load schema files."""
        lottie_path = temp_lottie_dir / "test-category" / "test-template.json"

        schema = load_schema(lottie_path)

        assert schema is not None
        assert schema["name"] == "Test Template"
        assert "message" in schema["fields"]

    def test_load_schema_nonexistent(self, sample_lottie):
        """Load returns None when no schema exists."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(sample_lottie, temp_path)
            schema = load_schema(temp_path)
            assert schema is None
        finally:
            Path(temp_path).unlink()


class TestRenderTemplate:
    """Tests for template rendering."""

    def test_render_template_text(self, temp_lottie_dir):
        """Render template with text field."""
        lottie_path = temp_lottie_dir / "test-category" / "test-template.json"

        result = render_template(
            lottie_path,
            message="Custom Message"
        )

        # Verify text was changed
        text_value = result["layers"][0]["t"]["d"]["k"][0]["s"]["t"]
        assert text_value == "Custom Message"

    def test_render_template_color(self, temp_lottie_dir):
        """Render template with color field."""
        lottie_path = temp_lottie_dir / "test-category" / "test-template.json"

        result = render_template(
            lottie_path,
            bg_color="#FF0000"
        )

        # Verify color was changed to red
        color_value = result["layers"][1]["shapes"][0]["it"][1]["c"]["k"]
        assert color_value[:3] == [1.0, 0.0, 0.0]

    def test_render_template_save_output(self, temp_lottie_dir):
        """Render template and save to file."""
        lottie_path = temp_lottie_dir / "test-category" / "test-template.json"
        output_path = temp_lottie_dir / "output.json"

        render_template(
            lottie_path,
            output_path,
            message="Saved Message"
        )

        assert output_path.exists()

        with open(output_path) as f:
            saved = json.load(f)

        text_value = saved["layers"][0]["t"]["d"]["k"][0]["s"]["t"]
        assert text_value == "Saved Message"

    def test_render_template_invalid_field(self, temp_lottie_dir):
        """Invalid field name raises ValueError."""
        lottie_path = temp_lottie_dir / "test-category" / "test-template.json"

        with pytest.raises(ValueError, match="Unknown field"):
            render_template(
                lottie_path,
                nonexistent_field="value"
            )

    def test_render_template_no_schema(self, sample_lottie):
        """Template without schema raises ValueError."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            save_lottie(sample_lottie, temp_path)

            with pytest.raises(ValueError, match="No schema found"):
                render_template(temp_path, field="value")
        finally:
            Path(temp_path).unlink()


class TestListTemplates:
    """Tests for template listing."""

    def test_list_templates(self, temp_lottie_dir):
        """List templates in directory."""
        templates = list_templates(temp_lottie_dir)

        assert len(templates) >= 1

        template = templates[0]
        assert "path" in template
        assert "category" in template
        assert "has_schema" in template
        assert "fields" in template

    def test_list_templates_schema_status(self, temp_lottie_dir):
        """Template with schema shows fields."""
        templates = list_templates(temp_lottie_dir)

        # Find our test template
        test_template = next(
            (t for t in templates if "test-template" in t["path"]),
            None
        )

        assert test_template is not None
        assert test_template["has_schema"] is True
        assert "message" in test_template["fields"]
        assert "bg_color" in test_template["fields"]


# =============================================================================
# Integration with Actual Assets
# =============================================================================

class TestActualLottieAssets:
    """Tests against actual Lottie assets in the project."""

    def test_magic_box_schema_exists(self):
        """Magic box template has a curated schema."""
        lottie_path = Path("assets/common/lottie/icons/magic-box.json")
        if not lottie_path.exists():
            pytest.skip("Lottie assets not available")

        schema = load_schema(lottie_path)
        assert schema is not None
        assert "message" in schema["fields"]
        assert "box_color" in schema["fields"]

    def test_modern_lower_third_schema(self):
        """Modern lower third has headline field."""
        lottie_path = Path("assets/common/lottie/lower-thirds/modern.json")
        if not lottie_path.exists():
            pytest.skip("Lottie assets not available")

        schema = load_schema(lottie_path)
        assert schema is not None
        assert "headline" in schema["fields"]

    def test_render_magic_box(self):
        """Can render magic box with custom values."""
        lottie_path = Path("assets/common/lottie/icons/magic-box.json")
        if not lottie_path.exists():
            pytest.skip("Lottie assets not available")

        result = render_template(
            lottie_path,
            message="TEST",
            box_color="#FF0000"
        )

        # Verify text changed
        text_value = result["layers"][0]["t"]["d"]["k"][0]["s"]["t"]
        assert text_value == "TEST"
