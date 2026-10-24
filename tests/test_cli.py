"""
Unit tests for the Click CLI interface (sentinel-dl).
"""

from click.testing import CliRunner

from smart_sentinel import __version__
from smart_sentinel.cli import main


def test_cli_version():
    """Verify version command matches __version__."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_help():
    """Verify CLI root help output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Sentinel-1 & Sentinel-2" in result.output
    assert "search" in result.output
    assert "download" in result.output
    assert "auth" in result.output


def test_cli_download_without_args_fails():
    """Verify download command fails gracefully if no IDs or file is provided."""
    runner = CliRunner()
    result = runner.invoke(main, ["download"])
    assert result.exit_code != 0
    assert "No product IDs provided" in result.output


def test_cli_search_help():
    """Verify search subcommand options."""
    runner = CliRunner()
    result = runner.invoke(main, ["search", "--help"])
    assert result.exit_code == 0
    assert "--bbox" in result.output
    assert "--start" in result.output
    assert "--max-cloud" in result.output
    assert "--export" in result.output


def test_cli_download_help():
    """Verify download subcommand options including composite."""
    runner = CliRunner()
    result = runner.invoke(main, ["download", "--help"])
    assert result.exit_code == 0
    assert "--bands" in result.output
    assert "--type" in result.output
    assert "--composite" in result.output

