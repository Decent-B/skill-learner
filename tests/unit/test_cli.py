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


def test_cli_ingest_pack_runs_with_local_text_source(tmp_path: Path) -> None:
    local_file = tmp_path / "sample.txt"
    local_file.write_text("mvn -B verify\n", encoding="utf-8")
    pack_file = tmp_path / "pack.yaml"
    pack_file.write_text(
        "\n".join(
            [
                "benchmark_id: fix-build-google-auto",
                "sources:",
                "  - id: L1",
                "    source_type: text",
                f"    path: {local_file}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"
    result = runner.invoke(
        app,
        [
            "ingest-pack",
            "--pack",
            str(pack_file),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--reports-dir",
            str(reports_dir),
        ],
    )
    assert result.exit_code == 0
    assert "Batch ingestion summary" in result.stdout


def test_cli_extract_preview_writes_artifacts(tmp_path: Path) -> None:
    local_file = tmp_path / "sample.txt"
    local_file.write_text("gradle build --stacktrace\n", encoding="utf-8")
    pack_file = tmp_path / "pack.yaml"
    pack_file.write_text(
        "\n".join(
            [
                "benchmark_id: fix-build-google-auto",
                "sources:",
                "  - id: L1",
                "    source_type: text",
                f"    path: {local_file}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "extract-preview",
            "--pack",
            str(pack_file),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--normalized-dir",
            str(tmp_path / "normalized"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )
    assert result.exit_code == 0
    assert "Extraction preview artifacts" in result.stdout
