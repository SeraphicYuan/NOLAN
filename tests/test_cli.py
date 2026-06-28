"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner
from pathlib import Path

from nolan.cli import main


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


def test_cli_has_version(runner):
    """CLI shows version."""
    result = runner.invoke(main, ['--version'])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_has_process_command(runner):
    """CLI has process command."""
    result = runner.invoke(main, ['process', '--help'])

    assert result.exit_code == 0
    assert "essay" in result.output.lower()


def test_cli_has_index_command(runner):
    """CLI has index command."""
    result = runner.invoke(main, ['index', '--help'])

    assert result.exit_code == 0
    assert "video" in result.output.lower() or "directory" in result.output.lower()


def test_cli_has_hub_command(runner):
    """CLI has the hub command (the unified web UI; legacy serve/browse/library
    standalone viewers were removed in favor of it)."""
    result = runner.invoke(main, ['hub', '--help'])

    assert result.exit_code == 0
    assert "port" in result.output.lower()
