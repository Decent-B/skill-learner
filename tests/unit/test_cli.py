"""Unit tests for CLI entrypoints."""

from __future__ import annotations

from typer.testing import CliRunner

from skill_learner.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Skill extraction and evaluation pipeline." in result.stdout


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "skill-learner" in result.stdout


def test_cli_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Environment diagnostics" in result.stdout
