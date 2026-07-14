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
    assert config.comfyui.port == 8080
    assert config.indexing.frame_interval == 5


def test_load_config_finds_repo_yaml_from_nested_cwd(monkeypatch):
    """From a nested working dir (e.g. render-service/.../bridge, where run_pool shells pool.py),
    load_config must still discover the repo-root nolan.yaml — NOT silently fall back to defaults.
    Regression for the homer CWD-config bug (stale indexing.database + wrong comfyui.port on the pool path)."""
    repo = Path(__file__).resolve().parents[1]
    if not (repo / "nolan.yaml").exists() and not (repo / "nolan.yml").exists():
        pytest.skip("no repo-root nolan.yaml to resolve against")
    root_cfg = load_config()                                   # pytest cwd = repo root
    nested = repo / "render-service" / "_lab_hyperframes" / "bridge"
    if not nested.is_dir():
        nested = repo / "src" / "nolan"
    monkeypatch.chdir(nested)
    nested_cfg = load_config()
    # the invariant: a nested CWD resolves the SAME config as the repo root
    assert nested_cfg.indexing.database == root_cfg.indexing.database
    assert nested_cfg.comfyui.port == root_cfg.comfyui.port


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
