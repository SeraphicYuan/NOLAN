"""Tests for the asset management system."""

import pytest
from pathlib import Path
import tempfile
import shutil

from nolan.assets import (
    AssetManager,
    asset_manager,
    get_asset,
    get_asset_content,
    get_icon,
    get_icon_content,
    list_assets,
    list_variants,
    _sanitize_path_component,
)


class TestSanitizePath:
    """Tests for path sanitization security."""

    def test_valid_name(self):
        """Valid names pass through."""
        assert _sanitize_path_component("check", allow_slash=False) == "check"
        assert _sanitize_path_component("arrow-up", allow_slash=False) == "arrow-up"
        assert _sanitize_path_component("icons/check.svg", allow_slash=True) == "icons/check.svg"

    def test_empty_name_raises(self):
        """Empty names raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            _sanitize_path_component("")

    def test_null_byte_raises(self):
        """Null bytes in name raise ValueError."""
        with pytest.raises(ValueError, match="null bytes"):
            _sanitize_path_component("file\x00.svg")

    def test_path_traversal_raises(self):
        """Path traversal attempts raise ValueError."""
        with pytest.raises(ValueError, match="path traversal"):
            _sanitize_path_component("../etc/passwd")
        with pytest.raises(ValueError, match="path traversal"):
            _sanitize_path_component("foo/../bar")
        with pytest.raises(ValueError, match="path traversal"):
            _sanitize_path_component("..\\windows\\system32")

    def test_absolute_path_raises(self):
        """Absolute paths raise ValueError."""
        with pytest.raises(ValueError, match="absolute path"):
            _sanitize_path_component("/etc/passwd")
        with pytest.raises(ValueError, match="absolute path"):
            _sanitize_path_component("C:\\Windows")

    def test_invalid_characters_raises(self):
        """Invalid characters raise ValueError."""
        with pytest.raises(ValueError, match="invalid characters"):
            _sanitize_path_component("file<name>.svg")
        with pytest.raises(ValueError, match="invalid characters"):
            _sanitize_path_component("file|name.svg")

    def test_slash_not_allowed(self):
        """Slashes raise when not allowed."""
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_path_component("icons/check.svg", allow_slash=False)

    def test_backslash_normalized(self):
        """Backslashes are normalized to forward slashes."""
        result = _sanitize_path_component("icons\\check.svg", allow_slash=True)
        assert result == "icons/check.svg"


class TestAssetManager:
    """Tests for AssetManager class."""

    @pytest.fixture
    def temp_assets(self):
        """Create a temporary assets directory structure."""
        temp_dir = tempfile.mkdtemp()
        assets_dir = Path(temp_dir) / "assets"

        # Create structure
        common_icons = assets_dir / "common" / "icons"
        common_icons.mkdir(parents=True)

        style_icons = assets_dir / "styles" / "test-style" / "icons"
        style_icons.mkdir(parents=True)

        # Create test files
        (common_icons / "check.svg").write_text('<svg>common check</svg>')
        (common_icons / "star.svg").write_text('<svg>common star</svg>')
        (common_icons / "arrow-ribbon.svg").write_text('<svg>ribbon variant</svg>')

        (style_icons / "check.svg").write_text('<svg>style check</svg>')

        yield assets_dir

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_get_asset_style_specific(self, temp_assets):
        """Style-specific assets are found first."""
        manager = AssetManager(temp_assets)
        path = manager.get_asset("test-style", "icons/check.svg")
        assert path is not None
        # Check path contains style folder (cross-platform)
        path_str = str(path).replace("\\", "/")
        assert "styles/test-style" in path_str
        assert path.read_text() == '<svg>style check</svg>'

    def test_get_asset_fallback_to_common(self, temp_assets):
        """Falls back to common when style-specific doesn't exist."""
        manager = AssetManager(temp_assets)
        path = manager.get_asset("test-style", "icons/star.svg")
        assert path is not None
        assert "common" in str(path)
        assert path.read_text() == '<svg>common star</svg>'

    def test_get_asset_not_found(self, temp_assets):
        """Returns None for non-existent assets."""
        manager = AssetManager(temp_assets)
        path = manager.get_asset("test-style", "icons/nonexistent.svg")
        assert path is None

    def test_get_asset_with_variant(self, temp_assets):
        """Variant parameter modifies asset name."""
        manager = AssetManager(temp_assets)
        # arrow.svg doesn't exist, but arrow-ribbon.svg does
        path = manager.get_asset("test-style", "icons/arrow.svg", variant="ribbon")
        assert path is not None
        assert path.read_text() == '<svg>ribbon variant</svg>'

    def test_get_asset_content(self, temp_assets):
        """Get asset content directly."""
        manager = AssetManager(temp_assets)
        content = manager.get_asset_content("test-style", "icons/check.svg")
        assert content == '<svg>style check</svg>'

    def test_get_icon_convenience(self, temp_assets):
        """get_icon adds icons/ prefix and .svg extension."""
        manager = AssetManager(temp_assets)
        path = manager.get_icon("test-style", "check")
        assert path is not None
        assert path.name == "check.svg"

    def test_get_icon_content(self, temp_assets):
        """get_icon_content returns SVG content."""
        manager = AssetManager(temp_assets)
        content = manager.get_icon_content("test-style", "star")
        assert content == '<svg>common star</svg>'

    def test_has_asset(self, temp_assets):
        """has_asset checks existence."""
        manager = AssetManager(temp_assets)
        assert manager.has_asset("test-style", "icons/check.svg") is True
        assert manager.has_asset("test-style", "icons/nonexistent.svg") is False

    def test_has_style_specific_asset(self, temp_assets):
        """has_style_specific_asset doesn't fall back to common."""
        manager = AssetManager(temp_assets)
        # check.svg exists in style
        assert manager.has_style_specific_asset("test-style", "icons/check.svg") is True
        # star.svg only exists in common
        assert manager.has_style_specific_asset("test-style", "icons/star.svg") is False

    def test_list_assets(self, temp_assets):
        """list_assets returns all assets for style."""
        manager = AssetManager(temp_assets)
        assets = manager.list_assets("test-style")
        assert "icons/check.svg" in assets or "icons\\check.svg" in assets
        assert "icons/star.svg" in assets or "icons\\star.svg" in assets

    def test_list_assets_with_category(self, temp_assets):
        """list_assets with category filters to subfolder."""
        manager = AssetManager(temp_assets)
        icons = manager.list_assets("test-style", category="icons")
        # Should contain icon files but normalized
        assert len(icons) >= 2

    def test_list_styles(self, temp_assets):
        """list_styles returns available style directories."""
        manager = AssetManager(temp_assets)
        styles = manager.list_styles()
        assert "test-style" in styles

    def test_list_common_assets(self, temp_assets):
        """list_common_assets returns common assets."""
        manager = AssetManager(temp_assets)
        assets = manager.list_common_assets()
        # Should include check.svg, star.svg, arrow-ribbon.svg
        assert len(assets) >= 3

    def test_list_variants(self, temp_assets):
        """list_variants returns variant suffixes."""
        manager = AssetManager(temp_assets)
        variants = manager.list_variants("test-style", "icons/arrow.svg")
        assert "ribbon" in variants

    def test_path_traversal_blocked(self, temp_assets):
        """Path traversal attempts are blocked."""
        manager = AssetManager(temp_assets)
        # These should return None due to path validation
        assert manager.get_asset("../etc", "passwd") is None
        assert manager.get_asset("test-style", "../../../etc/passwd") is None
        assert manager.get_asset("test-style", "icons/..\\..\\..\\etc\\passwd") is None


class TestGlobalAssetManager:
    """Tests for global singleton and convenience functions."""

    def test_global_manager_exists(self):
        """Global asset_manager singleton exists."""
        assert asset_manager is not None
        assert isinstance(asset_manager, AssetManager)

    def test_convenience_functions(self):
        """Convenience functions work with global manager."""
        # These test against the actual assets directory
        icons = list_assets("noir-essay", category="icons")
        # Should work without error
        assert isinstance(icons, list)

    def test_get_icon_from_common(self):
        """Can get icons from common folder."""
        # This tests the actual common icons we added
        content = get_icon_content("any-style", "check")
        if content:  # Only if assets exist
            assert "<svg" in content or "<polyline" in content


class TestActualAssets:
    """Tests against the actual assets in the project."""

    def test_common_icons_exist(self):
        """Common icons should exist in the assets folder."""
        expected_icons = ["check", "star", "arrow-up", "trending-up", "code", "database", "users", "zap", "award"]
        for icon_name in expected_icons:
            path = get_icon("any-style", icon_name)
            assert path is not None, f"Icon {icon_name} not found"
            assert path.exists(), f"Icon {icon_name} path exists but file doesn't"

    def test_icon_content_valid_svg(self):
        """Icon content should be valid SVG."""
        content = get_icon_content("any-style", "check")
        assert content is not None
        assert "<svg" in content
        assert "viewBox" in content

    def test_icons_use_current_color(self):
        """Icons should use currentColor for theming."""
        content = get_icon_content("any-style", "check")
        assert content is not None
        assert "currentColor" in content
