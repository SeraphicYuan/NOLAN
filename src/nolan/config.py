"""Configuration management for NOLAN."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class GeminiConfig:
    """Gemini API configuration."""
    api_key: str = ""
    model: str = "gemini-3-flash-preview"


@dataclass
class LLMConfig:
    """Default text-LLM for authoring tasks (script, scene design, clustering, etc.).

    Defaults to qwen/qwen3.7-plus via OpenRouter (cheaper than Gemini, strong quality).
    Override globally in nolan.yaml (`llm:` block) or per-run via CLI/webUI.
    """
    provider: str = "openrouter"   # openrouter (default) | gemini
    model: str = "qwen/qwen3.7-plus"
    reasoning_enabled: bool = False


@dataclass
class ComfyUIConfig:
    """ComfyUI connection configuration."""
    host: str = "127.0.0.1"
    port: int = 8188
    workflow: str = "default"
    width: int = 1920
    height: int = 1080
    steps: int = 20


@dataclass
class VisionConfig:
    """Vision provider configuration."""
    provider: str = "openrouter"  # openrouter, gemini, ollama
    model: str = "qwen/qwen3.7-plus"
    host: str = "127.0.0.1"  # Use IP, not hostname (Windows httpx issue)
    port: int = 11434
    timeout: float = 60.0
    # OpenRouter-specific (OpenAI-compatible endpoint)
    openrouter_api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    # Reasoning control for reasoning-capable OpenRouter models. Off by default
    # (~4-6x faster frame analysis with negligible quality loss).
    reasoning_enabled: bool = False
    reasoning_max_tokens: Optional[int] = None


@dataclass
class WhisperConfig:
    """Whisper transcription configuration."""
    enabled: bool = False  # Off by default (requires faster-whisper + ffmpeg)
    model_size: str = "base"  # tiny, base, small, medium, large-v2, large-v3
    device: str = "auto"  # auto, cpu, cuda
    compute_type: str = "auto"  # auto, int8, float16, float32
    language: Optional[str] = None  # None for auto-detect


@dataclass
class IndexingConfig:
    """Video indexing configuration."""
    frame_interval: int = 5
    database: str = "~/.nolan/library.db"
    sampling_strategy: str = "ffmpeg_scene"  # ffmpeg_scene (fast), hybrid, fixed, scene_change
    min_interval: float = 1.0
    max_interval: float = 30.0
    scene_threshold: float = 25.0  # For hybrid/scene_change samplers
    ffmpeg_scene_threshold: Optional[float] = None  # None = adaptive (5σ), or fixed 0-1
    enable_transcript: bool = True
    enable_inference: bool = True
    concurrency: int = 25


@dataclass
class DefaultsConfig:
    """Default processing settings."""
    words_per_minute: int = 150
    output_dir: str = "./output"


@dataclass
class ImageSourcesConfig:
    """Image/video search sources configuration (API keys)."""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    smithsonian_api_key: str = ""  # Get from api.data.gov
    # Additional providers (free keys) — set in .env to enable.
    europeana_api_key: str = ""    # https://pro.europeana.eu/pages/get-api
    dpla_api_key: str = ""         # https://pro.dp.la/developers/policies (email request)
    flickr_api_key: str = ""       # https://www.flickr.com/services/apps/create/
    unsplash_access_key: str = ""  # https://unsplash.com/developers
    rijksmuseum_api_key: str = ""  # https://data.rijksmuseum.nl/object-metadata/api/
    harvard_art_api_key: str = ""  # https://harvardartmuseums.org/collections/api
    coverr_api_key: str = ""       # https://coverr.co/ (API access)

    def provider_keys(self) -> dict:
        """Map for ImageSearchClient(keys=...)."""
        return {
            "europeana": self.europeana_api_key,
            "dpla": self.dpla_api_key,
            "flickr": self.flickr_api_key,
            "unsplash": self.unsplash_access_key,
            "rijksmuseum": self.rijksmuseum_api_key,
            "harvard": self.harvard_art_api_key,
            "coverr": self.coverr_api_key,
        }


@dataclass
class ClipMatchingConfig:
    """Clip matching configuration for matching scenes to video library."""
    candidates_per_scene: int = 3     # Top N candidates from vector search
    min_similarity: float = 0.5       # Minimum similarity threshold (0-1)
    search_level: str = "segments"    # segments, clusters, both
    skip_edge_percent: float = 0.07   # Skip first 7% of clip (avoid transitions)
    concurrency: int = 5             # Parallel scene matching (LLM calls)
    fast_path_min_similarity: float = 0.75  # Auto-accept very strong matches
    fast_path_margin: float = 0.15          # Min gap between top-2 to skip LLM


@dataclass
class NolanConfig:
    """Main configuration container."""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    image_sources: ImageSourcesConfig = field(default_factory=ImageSourcesConfig)
    clip_matching: ClipMatchingConfig = field(default_factory=ClipMatchingConfig)


def load_config(config_path: Optional[Path] = None) -> NolanConfig:
    """Load configuration from environment and optional YAML file.

    Args:
        config_path: Optional path to YAML config file.

    Returns:
        Populated NolanConfig instance.
    """
    # Load .env file from current directory
    load_dotenv()

    config = NolanConfig()

    # Load API keys from environment
    config.gemini.api_key = os.getenv("GEMINI_API_KEY", "")
    config.vision.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
    config.image_sources.pexels_api_key = os.getenv("PEXELS_API_KEY", "")
    config.image_sources.pixabay_api_key = os.getenv("PIXABAY_API_KEY", "")
    config.image_sources.smithsonian_api_key = os.getenv("SMITHSONIAN_API_KEY", "")
    config.image_sources.europeana_api_key = os.getenv("EUROPEANA_API_KEY", "")
    config.image_sources.dpla_api_key = os.getenv("DPLA_API_KEY", "")
    config.image_sources.flickr_api_key = os.getenv("FLICKR_API_KEY", "")
    config.image_sources.unsplash_access_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    config.image_sources.rijksmuseum_api_key = os.getenv("RIJKSMUSEUM_API_KEY", "")
    config.image_sources.harvard_art_api_key = os.getenv("HARVARD_ART_API_KEY", "")
    config.image_sources.coverr_api_key = os.getenv("COVERR_API_KEY", "")

    # Auto-detect config file if not provided
    if config_path is None:
        for name in ["nolan.yaml", "nolan.yml"]:
            candidate = Path(name)
            if candidate.exists():
                config_path = candidate
                break

    # Load YAML overrides if provided
    if config_path and config_path.exists():
        with open(config_path) as f:
            overrides = yaml.safe_load(f) or {}

        if "gemini" in overrides:
            for key, value in overrides["gemini"].items():
                if hasattr(config.gemini, key):
                    setattr(config.gemini, key, value)

        if "llm" in overrides:
            for key, value in overrides["llm"].items():
                if hasattr(config.llm, key):
                    setattr(config.llm, key, value)

        if "comfyui" in overrides:
            for key, value in overrides["comfyui"].items():
                if hasattr(config.comfyui, key):
                    setattr(config.comfyui, key, value)

        if "vision" in overrides:
            for key, value in overrides["vision"].items():
                if hasattr(config.vision, key):
                    setattr(config.vision, key, value)

        if "whisper" in overrides:
            for key, value in overrides["whisper"].items():
                if hasattr(config.whisper, key):
                    setattr(config.whisper, key, value)

        if "indexing" in overrides:
            for key, value in overrides["indexing"].items():
                if hasattr(config.indexing, key):
                    setattr(config.indexing, key, value)

        if "defaults" in overrides:
            for key, value in overrides["defaults"].items():
                if hasattr(config.defaults, key):
                    setattr(config.defaults, key, value)

        if "image_sources" in overrides:
            for key, value in overrides["image_sources"].items():
                if hasattr(config.image_sources, key):
                    setattr(config.image_sources, key, value)

        if "clip_matching" in overrides:
            for key, value in overrides["clip_matching"].items():
                if hasattr(config.clip_matching, key):
                    setattr(config.clip_matching, key, value)

    return config
