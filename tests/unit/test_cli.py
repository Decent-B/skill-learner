"""Unit tests for CLI entrypoints."""

from __future__ import annotations

from pathlib import Path

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


def test_cli_ingest_rejects_invalid_option_combo(tmp_path: Path) -> None:
    local_file = tmp_path / "sample.txt"
    local_file.write_text("hello", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "ingest",
            "--source-type",
            "web",
            "--path",
            str(local_file),
        ],
    )
    assert result.exit_code == 2
    assert "ingestion failed" in result.stdout
