"""Pytest configuration and fixtures."""

import os
import pytest
from pathlib import Path

@pytest.fixture
def sample_essay_path():
    """Path to the sample Venezuela essay."""
    return Path(r"D:\ClaudeProjects\NOLAN\draft-20260104-110039.md")

@pytest.fixture
def sample_essay(sample_essay_path):
    """Load sample essay content."""
    return sample_essay_path.read_text(encoding="utf-8")

@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory for tests."""
    output = tmp_path / "output"
    output.mkdir()
    return output
