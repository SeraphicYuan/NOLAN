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
import re

logger = logging.getLogger(__name__)

# Default assets directory (relative to project root)
DEFAULT_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"

# Valid characters for style_id and asset names (alphanumeric, dash, underscore, forward slash, dot)
VALID_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-./]+$')


def _sanitize_path_component(name: str, allow_slash: bool = False) -> str:
    """
    Sanitize a path component to prevent path traversal attacks.

    Args:
        name: The path component to sanitize
        allow_slash: Whether to allow forward slashes (for asset paths like "icons/check.svg")

    Returns:
        Sanitized name

    Raises:
        ValueError: If name contains invalid characters or path traversal attempts
    """
    if not name:
        raise ValueError("Name cannot be empty")

    # Check for null bytes
    if '\x00' in name:
        raise ValueError("Name cannot contain null bytes")

    # Check for path traversal attempts
    if '..' in name:
        raise ValueError("Name cannot contain '..' (path traversal)")

    # Normalize path separators
    name = name.replace('\\', '/')

    # Check for absolute paths
    if name.startswith('/') or (len(name) > 1 and name[1] == ':'):
        raise ValueError("Name cannot be an absolute path")

    # Validate characters
    if not VALID_NAME_PATTERN.match(name):
        raise ValueError(f"Name contains invalid characters: {name}")

    # Additional check: no slash if not allowed
    if not allow_slash and '/' in name:
        raise ValueError("Name cannot contain path separators")

    return name


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

    def get_asset(
        self,
        style_id: str,
        asset_name: str,
        variant: Optional[str] = None
    ) -> Optional[Path]:
        """
        Get asset path, with fallback to common assets.

        Lookup order:
        1. assets/styles/{style_id}/{asset_name} (with variant if specified)
        2. assets/common/{asset_name} (with variant if specified)

        Args:
            style_id: Style identifier (e.g., "noir-essay", "cold-data")
            asset_name: Asset filename or relative path (e.g., "card-bg.svg", "icons/check.svg")
            variant: Optional variant suffix (e.g., "ribbon" → "arrow-ribbon.svg")

        Returns:
            Path to asset file, or None if not found

        Raises:
            ValueError: If style_id or asset_name contain invalid characters
        """
        # Sanitize inputs to prevent path traversal
        try:
            style_id = _sanitize_path_component(style_id, allow_slash=False)
            asset_name = _sanitize_path_component(asset_name, allow_slash=True)
            if variant:
                variant = _sanitize_path_component(variant, allow_slash=False)
        except ValueError as e:
            logger.error(f"Invalid asset path: {e}")
            return None

        # Apply variant to asset name if specified
        if variant:
            # Insert variant before extension: "icons/arrow.svg" → "icons/arrow-ribbon.svg"
            path_obj = Path(asset_name)
            new_name = f"{path_obj.stem}-{variant}{path_obj.suffix}"
            if path_obj.parent != Path("."):
                asset_name = str(path_obj.parent / new_name)
            else:
                asset_name = new_name

        # Try style-specific first
        style_path = self.styles_dir / style_id / asset_name
        if style_path.exists():
            # Double-check the resolved path is still within assets_dir (defense in depth)
            try:
                style_path.resolve().relative_to(self.assets_dir.resolve())
            except ValueError:
                logger.error(f"Path traversal detected: {style_path}")
                return None
            logger.debug(f"Found style-specific asset: {style_path}")
            return style_path

        # Fall back to common
        common_path = self.common_dir / asset_name
        if common_path.exists():
            try:
                common_path.resolve().relative_to(self.assets_dir.resolve())
            except ValueError:
                logger.error(f"Path traversal detected: {common_path}")
                return None
            logger.debug(f"Found common asset: {common_path}")
            return common_path

        logger.warning(f"Asset not found: {asset_name} (style: {style_id})")
        return None

    def get_asset_content(
        self,
        style_id: str,
        asset_name: str,
        encoding: str = "utf-8",
        variant: Optional[str] = None
    ) -> Optional[str]:
        """
        Get asset file content as string.

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path
            encoding: File encoding (default: utf-8)
            variant: Optional variant suffix

        Returns:
            File content as string, or None if not found
        """
        path = self.get_asset(style_id, asset_name, variant=variant)
        if path is None:
            return None

        try:
            return path.read_text(encoding=encoding)
        except Exception as e:
            logger.error(f"Failed to read asset {path}: {e}")
            return None

    def get_asset_bytes(
        self,
        style_id: str,
        asset_name: str,
        variant: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Get asset file content as bytes (for binary files like PNG).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path
            variant: Optional variant suffix

        Returns:
            File content as bytes, or None if not found
        """
        path = self.get_asset(style_id, asset_name, variant=variant)
        if path is None:
            return None

        try:
            return path.read_bytes()
        except Exception as e:
            logger.error(f"Failed to read asset {path}: {e}")
            return None

    def has_asset(
        self,
        style_id: str,
        asset_name: str,
        variant: Optional[str] = None
    ) -> bool:
        """
        Check if an asset exists (style-specific or common).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path
            variant: Optional variant suffix

        Returns:
            True if asset exists
        """
        return self.get_asset(style_id, asset_name, variant=variant) is not None

    def has_style_specific_asset(self, style_id: str, asset_name: str) -> bool:
        """
        Check if a style-specific asset exists (not falling back to common).

        Args:
            style_id: Style identifier
            asset_name: Asset filename or relative path

        Returns:
            True if style-specific asset exists
        """
        # Sanitize inputs
        try:
            style_id = _sanitize_path_component(style_id, allow_slash=False)
            asset_name = _sanitize_path_component(asset_name, allow_slash=True)
        except ValueError:
            return False

        style_path = self.styles_dir / style_id / asset_name
        if not style_path.exists():
            return False

        # Verify path is within assets directory
        try:
            style_path.resolve().relative_to(self.assets_dir.resolve())
            return True
        except ValueError:
            return False

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

    def get_icon(
        self,
        style_id: str,
        icon_name: str,
        variant: Optional[str] = None
    ) -> Optional[Path]:
        """
        Convenience method to get an icon asset.

        Args:
            style_id: Style identifier
            icon_name: Icon name (with or without .svg extension)
            variant: Optional variant suffix

        Returns:
            Path to icon file
        """
        if not icon_name.endswith(".svg"):
            icon_name = f"{icon_name}.svg"
        return self.get_asset(style_id, f"icons/{icon_name}", variant=variant)

    def get_icon_content(
        self,
        style_id: str,
        icon_name: str,
        variant: Optional[str] = None
    ) -> Optional[str]:
        """
        Convenience method to get icon SVG content.

        Args:
            style_id: Style identifier
            icon_name: Icon name (with or without .svg extension)
            variant: Optional variant suffix

        Returns:
            SVG content as string
        """
        if not icon_name.endswith(".svg"):
            icon_name = f"{icon_name}.svg"
        return self.get_asset_content(style_id, f"icons/{icon_name}", variant=variant)

    def list_variants(self, style_id: str, asset_name: str) -> list[str]:
        """
        List available variants for an asset.

        For an asset "arrow.svg", variants might be "arrow-ribbon.svg", "arrow-3d.svg", etc.
        Returns variant suffixes like ["ribbon", "3d"].

        Args:
            style_id: Style identifier
            asset_name: Base asset name (e.g., "icons/arrow.svg")

        Returns:
            List of variant suffixes (empty list if no variants)
        """
        # Sanitize inputs
        try:
            style_id = _sanitize_path_component(style_id, allow_slash=False)
            asset_name = _sanitize_path_component(asset_name, allow_slash=True)
        except ValueError:
            return []

        variants = set()
        path_obj = Path(asset_name)
        base_stem = path_obj.stem
        suffix = path_obj.suffix
        parent = path_obj.parent

        # Check style-specific directory
        style_dir = self.styles_dir / style_id / parent
        if style_dir.exists():
            # Verify directory is within assets
            try:
                style_dir.resolve().relative_to(self.assets_dir.resolve())
                for f in style_dir.iterdir():
                    if f.is_file() and f.name.startswith(base_stem + "-") and f.suffix == suffix:
                        # Extract variant: "arrow-ribbon.svg" → "ribbon"
                        variant = f.stem[len(base_stem) + 1:]
                        if variant:
                            variants.add(variant)
            except ValueError:
                pass  # Path traversal attempt, skip

        # Check common directory
        common_dir = self.common_dir / parent
        if common_dir.exists():
            try:
                common_dir.resolve().relative_to(self.assets_dir.resolve())
                for f in common_dir.iterdir():
                    if f.is_file() and f.name.startswith(base_stem + "-") and f.suffix == suffix:
                        variant = f.stem[len(base_stem) + 1:]
                        if variant:
                            variants.add(variant)
            except ValueError:
                pass

        return sorted(variants)


# Global singleton instance
asset_manager = AssetManager()


# Convenience functions
def get_asset(
    style_id: str,
    asset_name: str,
    variant: Optional[str] = None
) -> Optional[Path]:
    """Get asset path using global manager."""
    return asset_manager.get_asset(style_id, asset_name, variant=variant)


def get_asset_content(
    style_id: str,
    asset_name: str,
    variant: Optional[str] = None
) -> Optional[str]:
    """Get asset content using global manager."""
    return asset_manager.get_asset_content(style_id, asset_name, variant=variant)


def get_icon(style_id: str, icon_name: str, variant: Optional[str] = None) -> Optional[Path]:
    """Get icon path using global manager."""
    return asset_manager.get_icon(style_id, icon_name, variant=variant)


def get_icon_content(style_id: str, icon_name: str, variant: Optional[str] = None) -> Optional[str]:
    """Get icon SVG content using global manager."""
    return asset_manager.get_icon_content(style_id, icon_name, variant=variant)


def list_assets(style_id: str, category: Optional[str] = None) -> list[str]:
    """List assets using global manager."""
    return asset_manager.list_assets(style_id, category)


def list_variants(style_id: str, asset_name: str) -> list[str]:
    """List asset variants using global manager."""
    return asset_manager.list_variants(style_id, asset_name)
