"""Command-line interface for the thesis pipeline."""

from __future__ import annotations

import platform
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from skill_learner import PACKAGE_NAME, __version__
from skill_learner.ingestion import (
    IngestionError,
    ingest_source,
    ingest_source_pack,
    write_batch_summary,
)
from skill_learner.ingestion.batch import benchmark_report_stem
from skill_learner.models import SourceType
from skill_learner.pipeline import run_extract_preview
from skill_learner.synthesis import synthesize_skill_from_preview, validate_skill_directory

app = typer.Typer(help="Skill extraction and evaluation pipeline.")
console = Console()

SOURCE_TYPE_OPTION = typer.Option(
    ...,
    "--source-type",
    case_sensitive=False,
    help="Source type to ingest: web, pdf, or text.",
)
URI_OPTION = typer.Option(
    None,
    "--uri",
    help="Remote URL for web ingestion.",
)
PATH_OPTION = typer.Option(
    None,
    "--path",
    help="Local file path for pdf/text ingestion.",
)
RAW_DIR_OPTION = typer.Option(
    Path("datasets/raw"),
    "--raw-dir",
    help="Directory to write extracted raw text files.",
)
MANIFEST_DIR_OPTION = typer.Option(
    Path("datasets/manifests"),
    "--manifest-dir",
    help="Directory to write manifest JSON files.",
)
PACK_PATH_OPTION = typer.Option(
    ...,
    "--pack",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Path to a benchmark source pack YAML file.",
)
NORMALIZED_DIR_OPTION = typer.Option(
    Path("datasets/normalized"),
    "--normalized-dir",
    help="Directory to write normalized JSON artifacts.",
)
REPORTS_DIR_OPTION = typer.Option(
    Path("reports/runs"),
    "--reports-dir",
    help="Directory for run summary and preview reports.",
)
SUMMARY_PATH_OPTION = typer.Option(
    None,
    "--summary-path",
    help="Optional explicit path for ingest summary JSON.",
)
PREVIEW_JSON_OPTION = typer.Option(
    ...,
    "--preview-json",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Phase-2 preview JSON used as synthesis input.",
)
OUTPUT_ROOT_OPTION = typer.Option(
    Path("skills/generated"),
    "--output-root",
    help="Root directory for generated skills.",
)
SKILL_NAME_OPTION = typer.Option(
    None,
    "--skill-name",
    help="Optional explicit skill directory/frontmatter name.",
)
VALIDATE_FLAG_OPTION = typer.Option(
    True,
    "--validate/--no-validate",
    help="Run `agentskills validate` after synthesis.",
)
MAX_STEPS_OPTION = typer.Option(
    24,
    "--max-steps",
    min=1,
    help="Maximum extracted steps to include in generated skill.",
)
SKILL_DIR_OPTION = typer.Option(
    ...,
    "--skill-dir",
    exists=True,
    file_okay=False,
    dir_okay=True,
    readable=True,
    help="Path to generated skill directory for validation.",
)


@app.command()
def version() -> None:
    """Print the installed package version."""
    console.print(f"{PACKAGE_NAME} {__version__}")


@app.command()
def doctor() -> None:
    """Show baseline runtime diagnostics."""
    table = Table(title="Environment diagnostics")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("package", PACKAGE_NAME)
    table.add_row("version", __version__)
    table.add_row("python", platform.python_version())
    table.add_row("cwd", str(Path.cwd()))
    console.print(table)


@app.command()
def ingest(
    source_type: SourceType = SOURCE_TYPE_OPTION,
    uri: str | None = URI_OPTION,
    path: Path | None = PATH_OPTION,
    raw_dir: Path = RAW_DIR_OPTION,
    manifest_dir: Path = MANIFEST_DIR_OPTION,
) -> None:
    """Ingest one source and persist raw text + manifest records."""
    try:
        record = ingest_source(
            source_type=source_type,
            uri=uri,
            path=path,
            raw_dir=raw_dir,
            manifest_dir=manifest_dir,
        )
    except (IngestionError, ValueError) as exc:
        console.print(f"[red]ingestion failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(title="Ingestion result")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("source_id", record.source_id)
    table.add_row("source_type", record.metadata.source_type.value)
    table.add_row("byte_size", str(record.metadata.byte_size))
    table.add_row("raw_path", record.storage_path)
    table.add_row("manifest_path", record.manifest_path)
    console.print(table)


@app.command()
def ingest_pack(
    pack: Path = PACK_PATH_OPTION,
    raw_dir: Path = RAW_DIR_OPTION,
    manifest_dir: Path = MANIFEST_DIR_OPTION,
    reports_dir: Path = REPORTS_DIR_OPTION,
    summary_path: Path | None = SUMMARY_PATH_OPTION,
) -> None:
    """Ingest all sources from a YAML pack and write a run summary."""
    try:
        summary = ingest_source_pack(
            pack_path=pack,
            raw_dir=raw_dir,
            manifest_dir=manifest_dir,
        )
    except (IngestionError, ValueError, ValidationError) as exc:
        console.print(f"[red]pack ingestion failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    out_path = summary_path
    if out_path is None:
        stem = benchmark_report_stem(summary.benchmark_id)
        out_path = reports_dir / f"{stem}_ingest_summary.json"
    write_batch_summary(summary, summary_path=out_path)

    table = Table(title="Batch ingestion summary")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("benchmark_id", summary.benchmark_id)
    table.add_row("total_sources", str(summary.total_sources))
    table.add_row("succeeded", str(summary.succeeded))
    table.add_row("failed", str(summary.failed))
    table.add_row("summary_path", str(out_path.resolve()))
    console.print(table)


@app.command()
def extract_preview(
    pack: Path = PACK_PATH_OPTION,
    raw_dir: Path = RAW_DIR_OPTION,
    manifest_dir: Path = MANIFEST_DIR_OPTION,
    normalized_dir: Path = NORMALIZED_DIR_OPTION,
    reports_dir: Path = REPORTS_DIR_OPTION,
) -> None:
    """Run ingest + normalize + extraction and emit preview JSON/Markdown."""
    try:
        ingest_summary_path, preview_json_path, preview_markdown_path = run_extract_preview(
            pack_path=pack,
            raw_dir=raw_dir,
            manifest_dir=manifest_dir,
            normalized_dir=normalized_dir,
            reports_dir=reports_dir,
        )
    except (IngestionError, OSError, ValueError, ValidationError) as exc:
        console.print(f"[red]extract preview failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(title="Extraction preview artifacts")
    table.add_column("Artifact")
    table.add_column("Path")
    table.add_row("ingest_summary", str(ingest_summary_path))
    table.add_row("preview_json", str(preview_json_path))
    table.add_row("preview_markdown", str(preview_markdown_path))
    console.print(table)


@app.command()
def synthesize(
    preview_json: Path = PREVIEW_JSON_OPTION,
    output_root: Path = OUTPUT_ROOT_OPTION,
    skill_name: str | None = SKILL_NAME_OPTION,
    validate: bool = VALIDATE_FLAG_OPTION,
    max_steps: int = MAX_STEPS_OPTION,
) -> None:
    """Generate a skill package from extraction preview JSON."""
    try:
        result = synthesize_skill_from_preview(
            preview_json=preview_json,
            output_root=output_root,
            skill_name=skill_name,
            validate=validate,
            max_steps=max_steps,
        )
    except (OSError, RuntimeError, ValueError, ValidationError) as exc:
        console.print(f"[red]synthesis failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(title="Synthesis artifacts")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("skill_dir", result.skill_dir)
    table.add_row("skill_md_path", result.skill_md_path)
    table.add_row("reference_path", result.reference_path)
    table.add_row("selected_step_count", str(result.selected_step_count))
    table.add_row("validation_ran", str(result.validation_ran))
    table.add_row("validation_ok", str(result.validation_ok))
    console.print(table)


@app.command("validate-skill")
def validate_skill(skill_dir: Path = SKILL_DIR_OPTION) -> None:
    """Validate an existing skill directory against Agent Skills spec."""
    try:
        is_valid, output = validate_skill_directory(skill_dir.resolve())
    except RuntimeError as exc:
        console.print(f"[red]validation failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if is_valid:
        table = Table(title="Skill validation")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("skill_dir", str(skill_dir.resolve()))
        table.add_row("valid", "True")
        table.add_row("details", output or "(no output)")
        console.print(table)
        return

    console.print(f"[red]skill is invalid:[/red]\n{output}")
    raise typer.Exit(code=1)


def main() -> None:
    """Run CLI app."""
    app()


if __name__ == "__main__":
    main()
