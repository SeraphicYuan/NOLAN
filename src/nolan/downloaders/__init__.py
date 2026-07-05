"""Lottie template models + shared download utilities.

The one-off scraper downloaders (Jitter/LottieFiles/Lottieflow browser
automation) were removed in the Phase 6 cleanup — they had no callers. The
models and utilities remain in use (catalog building, rate limiting,
filename/metadata helpers).
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
]
