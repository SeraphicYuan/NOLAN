"""Tests for configuration loading."""

import pytest
from pathlib import Path

from nolan.config import load_config, NolanConfig


def test_load_config_from_env(monkeypatch, tmp_path):
    """Config loads GEMINI_API_KEY from environment."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    config = load_config()

    assert config.gemini.api_key == "test-api-key"


def test_config_has_defaults():
    """Config provides sensible defaults."""
    config = load_config()

    assert config.gemini.model == "gemini-3-flash-preview"
    assert config.defaults.words_per_minute == 150
    assert config.comfyui.host == "127.0.0.1"
    assert config.comfyui.port == 8188
    assert config.indexing.frame_interval == 5


def test_load_config_from_yaml(tmp_path, monkeypatch):
    """Config loads overrides from YAML file."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
defaults:
  words_per_minute: 120
""")

    config = load_config(config_path=config_file)

    assert config.defaults.words_per_minute == 120
