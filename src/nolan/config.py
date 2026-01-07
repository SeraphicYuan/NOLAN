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
class IndexingConfig:
    """Video indexing configuration."""
    frame_interval: int = 5
    database: str = "~/.nolan/library.db"


@dataclass
class DefaultsConfig:
    """Default processing settings."""
    words_per_minute: int = 150
    output_dir: str = "./output"


@dataclass
class NolanConfig:
    """Main configuration container."""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    comfyui: ComfyUIConfig = field(default_factory=ComfyUIConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


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

    # Load API key from environment
    config.gemini.api_key = os.getenv("GEMINI_API_KEY", "")

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

        if "indexing" in overrides:
            for key, value in overrides["indexing"].items():
                if hasattr(config.indexing, key):
                    setattr(config.indexing, key, value)

        if "defaults" in overrides:
            for key, value in overrides["defaults"].items():
                if hasattr(config.defaults, key):
                    setattr(config.defaults, key, value)

    return config
