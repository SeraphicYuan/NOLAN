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
    provider: str = "ollama"  # ollama, gemini
    model: str = "qwen3-vl:8b"
    host: str = "127.0.0.1"  # Use IP, not hostname (Windows httpx issue)
    port: int = 11434
    timeout: float = 60.0


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
    ffmpeg_scene_threshold: float = 0.3  # For ffmpeg_scene sampler (0-1)
    enable_transcript: bool = True
    enable_inference: bool = True


@dataclass
class DefaultsConfig:
    """Default processing settings."""
    words_per_minute: int = 150
    output_dir: str = "./output"


@dataclass
class ImageSourcesConfig:
    """Image search sources configuration."""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    smithsonian_api_key: str = ""  # Get from api.data.gov


@dataclass
class NolanConfig:
    """Main configuration container."""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    image_sources: ImageSourcesConfig = field(default_factory=ImageSourcesConfig)


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
    config.image_sources.pexels_api_key = os.getenv("PEXELS_API_KEY", "")
    config.image_sources.pixabay_api_key = os.getenv("PIXABAY_API_KEY", "")
    config.image_sources.smithsonian_api_key = os.getenv("SMITHSONIAN_API_KEY", "")

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

    return config
