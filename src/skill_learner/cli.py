"""Command-line interface for the thesis pipeline."""

from __future__ import annotations

import platform
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from skill_learner import PACKAGE_NAME, __version__
from skill_learner.ingestion import IngestionError, ingest_source
from skill_learner.models import SourceType

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


def main() -> None:
    """Run CLI app."""
    app()


if __name__ == "__main__":
    main()
