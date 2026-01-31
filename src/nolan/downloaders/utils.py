"""Shared utilities for Lottie downloaders."""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Protocol, TypeVar

from nolan.downloaders.models import BaseLottieTemplate


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Convert a name to a safe filename.

    Args:
        name: Original name to sanitize.
        max_length: Maximum filename length.

    Returns:
        Safe filename string (lowercase, hyphens instead of spaces).
    """
    # Remove invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace whitespace with hyphens
    name = re.sub(r'\s+', '-', name.strip())
    # Collapse multiple hyphens
    name = re.sub(r'-+', '-', name)
    # Lowercase and truncate
    return name.lower()[:max_length]


def extract_lottie_metadata(data: dict) -> dict:
    """Extract common metadata from Lottie JSON data.

    Args:
        data: Parsed Lottie JSON dictionary.

    Returns:
        Dictionary with width, height, fps, duration_seconds, layer_count.
    """
    fps = data.get("fr", 0)
    ip = data.get("ip", 0)  # in-point (start frame)
    op = data.get("op", 0)  # out-point (end frame)
    frames = op - ip

    return {
        "width": data.get("w", 0),
        "height": data.get("h", 0),
        "fps": fps,
        "frames": frames,
        "duration_seconds": round(frames / fps, 2) if fps > 0 else 0,
        "layer_count": len(data.get("layers", [])),
    }


def save_lottie_json(data: dict, output_path: Path, minify: bool = True) -> int:
    """Save Lottie JSON to file.

    Args:
        data: Lottie JSON data.
        output_path: Path to save to.
        minify: If True, save without whitespace.

    Returns:
        File size in bytes.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        if minify:
            json.dump(data, f, separators=(",", ":"))
        else:
            json.dump(data, f, indent=2)

    return output_path.stat().st_size


T = TypeVar('T', bound=BaseLottieTemplate)


class CatalogBuilder:
    """Build catalog JSON files from downloaded templates."""

    def __init__(self, source_name: str, output_dir: Path):
        """Initialize catalog builder.

        Args:
            source_name: Name of the download source (e.g., "jitter.video").
            output_dir: Base output directory for the catalog.
        """
        self.source_name = source_name
        self.output_dir = output_dir

    def build(
        self,
        templates: List[BaseLottieTemplate],
        catalog_filename: str = "catalog.json"
    ) -> dict:
        """Build and save a catalog from templates.

        Args:
            templates: List of downloaded templates.
            catalog_filename: Name of the catalog file.

        Returns:
            Catalog dictionary.
        """
        catalog = {
            "source": self.source_name,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(templates),
            "categories": {},
        }

        for template in templates:
            cat = template.category
            if cat not in catalog["categories"]:
                catalog["categories"][cat] = []

            catalog["categories"][cat].append(template.to_catalog_entry())

        # Save catalog
        catalog_path = self.output_dir / catalog_filename
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)

        print(f"Catalog saved: {catalog_path}")
        return catalog


class RateLimiter:
    """Simple rate limiter to avoid getting blocked."""

    def __init__(self, requests_per_minute: int = 20):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute.
        """
        self.min_interval = 60.0 / requests_per_minute
        self.last_request = 0.0

    def wait(self):
        """Wait if necessary to respect rate limit."""
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self.last_request = time.time()

    async def wait_async(self):
        """Async version of wait."""
        import asyncio
        now = time.time()
        elapsed = now - self.last_request
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            await asyncio.sleep(sleep_time)
        self.last_request = time.time()
