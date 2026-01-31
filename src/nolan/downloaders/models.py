"""Shared data models for Lottie downloaders."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BaseLottieTemplate:
    """Base template metadata shared across all downloaders.

    Subclasses can add source-specific fields.
    """
    id: str
    name: str
    category: str
    source_url: str = ""
    cdn_url: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    duration_seconds: float = 0
    file_size_bytes: int = 0
    local_path: str = ""
    downloaded_at: str = ""

    def to_catalog_entry(self) -> dict:
        """Convert to dictionary for catalog export."""
        return {
            "id": self.id,
            "name": self.name,
            "source_url": self.source_url,
            "cdn_url": self.cdn_url,
            "local_path": self.local_path,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "file_size_bytes": self.file_size_bytes,
            "downloaded_at": self.downloaded_at,
        }


@dataclass
class JitterTemplate(BaseLottieTemplate):
    """Template metadata for Jitter.video."""
    artboard_id: str = ""

    @property
    def url(self) -> str:
        """Alias for source_url for backwards compatibility."""
        return self.source_url


@dataclass
class LottieflowTemplate(BaseLottieTemplate):
    """Template metadata for Lottieflow/Finsweet."""
    page_url: str = ""

    def to_catalog_entry(self) -> dict:
        entry = super().to_catalog_entry()
        entry["page_url"] = self.page_url
        return entry


@dataclass
class LottieFilesMetadata(BaseLottieTemplate):
    """Metadata for LottieFiles.com downloads."""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    license: str = "Lottie Simple License"
    content_hash: str = ""
    color_palette: list[str] = field(default_factory=list)
    layer_count: int = 0
    has_expressions: bool = False
    has_images: bool = False
    frames: int = 0
    file_size_kb: float = 0

    # Legacy property aliases
    @property
    def title(self) -> str:
        return self.name

    @title.setter
    def title(self, value: str):
        self.name = value

    def to_catalog_entry(self) -> dict:
        entry = super().to_catalog_entry()
        entry.update({
            "author": self.author,
            "tags": self.tags,
            "license": self.license,
            "content_hash": self.content_hash,
            "color_palette": self.color_palette,
            "layer_count": self.layer_count,
            "has_expressions": self.has_expressions,
            "has_images": self.has_images,
        })
        return entry
