"""Lottie animation downloaders for various sources.

This package provides downloaders for:
- Jitter.video (browser automation)
- LottieFiles.com (HTTP scraping)
- Lottieflow/Finsweet (browser automation)

Example usage:
    # Using LottieFiles downloader (synchronous)
    from nolan.downloaders import LottieFilesDownloader

    downloader = LottieFilesDownloader()
    meta = downloader.download("https://lottiefiles.com/...", "category")

    # Using Jitter downloader (async)
    from nolan.downloaders import JitterDownloader

    async with JitterDownloader() as downloader:
        templates = await downloader.discover_templates("video-titles")
        for t in templates:
            await downloader.download_template(t)
"""

from nolan.downloaders.models import (
    BaseLottieTemplate,
    JitterTemplate,
    LottieflowTemplate,
    LottieFilesMetadata,
)
from nolan.downloaders.utils import (
    sanitize_filename,
    extract_lottie_metadata,
    save_lottie_json,
    CatalogBuilder,
    RateLimiter,
)

# Re-export downloaders for convenience
# These are imported lazily to avoid requiring all dependencies
def __getattr__(name):
    """Lazy import of downloader classes."""
    if name == "JitterDownloader":
        from nolan.jitter_downloader import JitterDownloader
        return JitterDownloader
    elif name == "LottieFilesDownloader":
        from nolan.lottie_downloader import LottieFilesDownloader
        return LottieFilesDownloader
    elif name == "LottieflowDownloader":
        from nolan.lottieflow_downloader import LottieflowDownloader
        return LottieflowDownloader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models
    "BaseLottieTemplate",
    "JitterTemplate",
    "LottieflowTemplate",
    "LottieFilesMetadata",
    # Utilities
    "sanitize_filename",
    "extract_lottie_metadata",
    "save_lottie_json",
    "CatalogBuilder",
    "RateLimiter",
    # Downloaders (lazy loaded)
    "JitterDownloader",
    "LottieFilesDownloader",
    "LottieflowDownloader",
]
