"""
Asset Management System

Simple file-based asset manager for style-specific visual assets.
Assets are organized by style with fallback to common assets.

Folder structure:
    assets/
        styles/
            noir-essay/
                staircase-arrow.svg
                card-bg.svg
                icons/
            cold-data/
                ...
        common/
            icons/
                check.svg
                star.svg
            shapes/
                arrow-segment.svg

Usage:
    from nolan.assets import asset_manager

    # Get asset path (falls back to common if style-specific doesn't exist)
    path = asset_manager.get_asset("noir-essay", "icons/check.svg")

    # Get asset content
    svg_content = asset_manager.get_asset_content("noir-essay", "card-bg.svg")

    # List available assets for a style
    assets = asset_manager.list_assets("noir-essay")

    # Check if asset exists
    exists = asset_manager.has_asset("noir-essay", "staircase-arrow.svg")
"""

from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default assets directory (relative to project root)
DEFAULT_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"


class AssetManager:
    """
    Simple file-based asset manager with style-specific lookups and common fallback.
    """

    def __init__(self, assets_dir: Optional[Path] = None):
        """
        Initialize AssetManager.

        Args:
            assets_dir: Path to assets directory. Defaults to project's assets/ folder.
        """
        self.assets_dir = Path(assets_dir) if assets_dir else DEFAULT_ASSETS_DIR
        self.styles_dir = self.assets_dir / "styles"
        self.common_dir = self.assets_dir / "common"

        # Ensure directories exist
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.styles_dir.mkdir(parents=True, exist_ok=True)
        self.common_dir.mkdir(parents=True, exist_ok=True)

    def get_asset(self, style_id: str, asset_name: str) -> Optional[Path]:
        """
        Get asset path, with fallback to common assets.

        Lookup order:
        1. assets/styles/{style_id}/{asset_name}
        2. assets/common/{asset_name}

        Args:
            style_id: Style identifier (e.g., "noir-essay", "cold-data")
            asset_name: Asset filename or relative path (e.g., "card-bg.svg", "icons/check.svg")

        Returns:
            Path to asset file, or None if not found
        """
        # Try style-specific first
        style_path = self.styles_dir / style_id / asset_name
        if style_path.exists():
            logger.debug(f"Found style-specific asset: {style_path}")
            return style_path

        # Fall back to common
        common_path = self.common_dir / asset_name
        if common_path.exists():
            logger.debug(f"Found common asset: {common_path}")
            return common_path

        logger.warning(f"Asset not found: {asset_name} (style: {style_id})")
        return None

    def get_asset_content(self, style_id: str, asset_name: str, encoding: str = "utf-8") -> Optional[str]:
        """
        Get asset file content as string.

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path
            encoding: File encoding (default: utf-8)

        Returns:
            File content as string, or None if not found
        """
        path = self.get_asset(style_id, asset_name)
        if path is None:
            return None

        try:
            return path.read_text(encoding=encoding)
        except Exception as e:
            logger.error(f"Failed to read asset {path}: {e}")
            return None

    def get_asset_bytes(self, style_id: str, asset_name: str) -> Optional[bytes]:
        """
        Get asset file content as bytes (for binary files like PNG).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path

        Returns:
            File content as bytes, or None if not found
        """
        path = self.get_asset(style_id, asset_name)
        if path is None:
            return None

        try:
            return path.read_bytes()
        except Exception as e:
            logger.error(f"Failed to read asset {path}: {e}")
            return None

    def has_asset(self, style_id: str, asset_name: str) -> bool:
        """
        Check if an asset exists (style-specific or common).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path

        Returns:
            True if asset exists
        """
        return self.get_asset(style_id, asset_name) is not None

    def has_style_specific_asset(self, style_id: str, asset_name: str) -> bool:
        """
        Check if a style-specific asset exists (not falling back to common).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path

        Returns:
            True if style-specific asset exists
        """
        style_path = self.styles_dir / style_id / asset_name
        return style_path.exists()

    def list_assets(self, style_id: str, category: Optional[str] = None) -> list[str]:
        """
        List available assets for a style (including common assets).

        Args:
            style_id: Style identifier
            category: Optional subfolder to list (e.g., "icons", "shapes")

        Returns:
            List of asset names (relative paths)
        """
        assets = set()

        # Style-specific assets
        style_dir = self.styles_dir / style_id
        if category:
            style_dir = style_dir / category
        if style_dir.exists():
            for path in style_dir.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(self.styles_dir / style_id)
                    assets.add(str(rel_path))

        # Common assets
        common_dir = self.common_dir
        if category:
            common_dir = common_dir / category
        if common_dir.exists():
            for path in common_dir.rglob("*"):
                if path.is_file():
                    rel_path = path.relative_to(self.common_dir)
                    assets.add(str(rel_path))

        return sorted(assets)

    def list_styles(self) -> list[str]:
        """
        List all available styles that have assets.

        Returns:
            List of style identifiers
        """
        if not self.styles_dir.exists():
            return []

        return sorted([
            d.name for d in self.styles_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

    def list_common_assets(self, category: Optional[str] = None) -> list[str]:
        """
        List common assets (available to all styles).

        Args:
            category: Optional subfolder to list

        Returns:
            List of asset names
        """
        common_dir = self.common_dir
        if category:
            common_dir = common_dir / category

        if not common_dir.exists():
            return []

        assets = []
        for path in common_dir.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.common_dir)
                assets.append(str(rel_path))

        return sorted(assets)

    def get_icon(self, style_id: str, icon_name: str) -> Optional[Path]:
        """
        Convenience method to get an icon asset.

        Args:
            style_id: Style identifier
            icon_name: Icon name (with or without .svg extension)

        Returns:
            Path to icon file
        """
        if not icon_name.endswith(".svg"):
            icon_name = f"{icon_name}.svg"
        return self.get_asset(style_id, f"icons/{icon_name}")

    def get_icon_content(self, style_id: str, icon_name: str) -> Optional[str]:
        """
        Convenience method to get icon SVG content.

        Args:
            style_id: Style identifier
            icon_name: Icon name (with or without .svg extension)

        Returns:
            SVG content as string
        """
        if not icon_name.endswith(".svg"):
            icon_name = f"{icon_name}.svg"
        return self.get_asset_content(style_id, f"icons/{icon_name}")


# Global singleton instance
asset_manager = AssetManager()


# Convenience functions
def get_asset(style_id: str, asset_name: str) -> Optional[Path]:
    """Get asset path using global manager."""
    return asset_manager.get_asset(style_id, asset_name)


def get_asset_content(style_id: str, asset_name: str) -> Optional[str]:
    """Get asset content using global manager."""
    return asset_manager.get_asset_content(style_id, asset_name)


def get_icon(style_id: str, icon_name: str) -> Optional[Path]:
    """Get icon path using global manager."""
    return asset_manager.get_icon(style_id, icon_name)


def list_assets(style_id: str, category: Optional[str] = None) -> list[str]:
    """List assets using global manager."""
    return asset_manager.list_assets(style_id, category)
