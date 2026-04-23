"""Command-line interface for web-cybersecurity connector ingestion."""

from __future__ import annotations

import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.table import Table

from skill_learner import PACKAGE_NAME, __version__
from skill_learner.connectors import collect_pack, load_connector_pack, supported_sources
from skill_learner.env import load_environment
from skill_learner.models import DataSource, RunStatus
from skill_learner.synthesis import (
    SynthesisMode,
    run_hackerone_skill_package_pipeline,
)

app = typer.Typer(help="Web cybersecurity data ingestion through production connectors.")
console = Console()

PACK_OPTION = typer.Option(
    ...,
    "--pack",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Connector pack YAML file path.",
)
OUTPUT_ROOT_OPTION = typer.Option(
    Path("datasets/cybersecurity_records"),
    "--output-root",
    help="Directory where connector snapshots and metadata will be written.",
)
MAX_CONCURRENT_JOBS_OPTION = typer.Option(
    None,
    "--max-concurrent-jobs",
    min=1,
    help="Override connector-pack max_concurrent_jobs for this run.",
)
DATASET_ROOT_OPTION = typer.Option(
    Path("datasets/cybersecurity_records"),
    "--dataset-root",
    exists=True,
    file_okay=False,
    dir_okay=True,
    readable=True,
    help="Dataset root containing benchmark source output directories.",
)
SKILLS_OUTPUT_ROOT_OPTION = typer.Option(
    Path("skills/generated"),
    "--output-root",
    help="Root directory where generated skill packages are written.",
)
HACKERONE_JSONL_OPTION = typer.Option(
    None,
    "--hackerone-jsonl",
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="Optional explicit HackerOne JSONL input path.",
)
LINE_INDEX_OPTION = typer.Option(
    [],
    "--line-index",
    help="1-based line index in HackerOne JSONL input. Repeatable.",
)
RECORD_KEY_OPTION = typer.Option(
    [],
    "--record-key",
    help="HackerOne source_record_id or record_uid. Repeatable.",
)


@dataclass
class JobProgress:
    """Mutable live status for one connector source."""

    status: str = "pending"
    records: int = 0
    error: str | None = None


@app.command()
def version() -> None:
    """Print the installed package version."""
    console.print(f"{PACKAGE_NAME} {__version__}")


@app.command()
def doctor() -> None:
    """Show runtime diagnostics."""
    loaded_env_files = load_environment()

    table = Table(title="Environment diagnostics")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("package", PACKAGE_NAME)
    table.add_row("version", __version__)
    table.add_row("python", platform.python_version())
    table.add_row("cwd", str(Path.cwd()))
    table.add_row(
        "env_files_loaded",
        ", ".join(str(path) for path in loaded_env_files) if loaded_env_files else "-",
    )
    table.add_row("NVD_API_KEY configured", str(bool(os.getenv("NVD_API_KEY"))))
    table.add_row("GITHUB_TOKEN configured", str(bool(os.getenv("GITHUB_TOKEN"))))
    console.print(table)


@app.command("list-connectors")
def list_connectors() -> None:
    """List all implemented source connectors."""
    table = Table(title="Supported connectors")
    table.add_column("Source")
    for source in supported_sources():
        table.add_row(source.value)
    console.print(table)


@app.command("validate-pack")
def validate_pack(pack: Path = PACK_OPTION) -> None:
    """Validate connector-pack schema and print parsed jobs."""
    try:
        parsed = load_connector_pack(pack)
    except (ValidationError, ValueError, OSError) as exc:
        console.print(f"[red]Pack validation failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(title="Validated connector pack")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("benchmark_id", parsed.benchmark_id)
    table.add_row("job_count", str(len(parsed.jobs)))
    table.add_row("max_concurrent_jobs", str(parsed.max_concurrent_jobs))
    table.add_row("pack", str(pack.resolve()))
    console.print(table)

    jobs_table = Table(title="Jobs")
    jobs_table.add_column("Source")
    jobs_table.add_column("Enabled")
    jobs_table.add_column("Max records")
    for job in parsed.jobs:
        jobs_table.add_row(job.source, str(job.enabled), str(job.max_records))
    console.print(jobs_table)


@app.command()
def collect(
    pack: Path = PACK_OPTION,
    output_root: Path = OUTPUT_ROOT_OPTION,
    max_concurrent_jobs: int | None = MAX_CONCURRENT_JOBS_OPTION,
) -> None:
    """Execute every connector job declared in the provided connector pack."""
    try:
        parsed_pack = load_connector_pack(pack)
    except (ValidationError, ValueError, OSError) as exc:
        console.print(f"[red]Collection failed before execution:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    status_styles = {
        "pending": "yellow",
        "running": "cyan",
        "success": "green",
        "failed": "red",
        "skipped": "magenta",
    }
    progress_order = [DataSource(job.source) for job in parsed_pack.jobs]
    progress_state: dict[DataSource, JobProgress] = {
        source: JobProgress() for source in progress_order
    }
    progress_lock = Lock()

    def render_progress_table() -> Table:
        table = Table(title=f"Live progress: {parsed_pack.benchmark_id}")
        table.add_column("Source")
        table.add_column("Status")
        table.add_column("Records")
        table.add_column("Error")
        for source in progress_order:
            state = progress_state[source]
            status_style = status_styles.get(state.status, "white")
            table.add_row(
                source.value,
                f"[{status_style}]{state.status}[/{status_style}]",
                str(state.records),
                state.error or "-",
            )
        return table

    def on_progress(
        source: DataSource,
        status: str,
        record_count: int,
        error: str | None,
    ) -> None:
        with progress_lock:
            state = progress_state.setdefault(source, JobProgress())
            state.status = status
            state.records = max(state.records, record_count)
            if error is not None:
                state.error = error
            elif status in {"success", "skipped"}:
                state.error = None

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                collect_pack,
                pack=parsed_pack,
                output_root=output_root,
                max_concurrent_jobs=max_concurrent_jobs,
                progress_callback=on_progress,
            )
            with Live(render_progress_table(), console=console, refresh_per_second=4) as live:
                while not future.done():
                    with progress_lock:
                        live.update(render_progress_table())
                    time.sleep(0.2)
                with progress_lock:
                    live.update(render_progress_table())
            summaries = future.result()
    except Exception as exc:
        console.print(f"[red]Collection failed during execution:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"Connector run summary: {parsed_pack.benchmark_id}")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Records")
    table.add_column("Output")
    table.add_column("Error")

    has_failure = False
    for summary in summaries:
        if summary.status is RunStatus.FAILED:
            has_failure = True
        table.add_row(
            summary.source.value,
            summary.status.value,
            str(summary.record_count),
            summary.output_path or "-",
            summary.error or "-",
        )
    console.print(table)

    if has_failure:
        raise typer.Exit(code=1)


@app.command("build-hackerone-skill-package")
def build_hackerone_skill_package(
    benchmark_id: str = typer.Option(
        "web-cybersecurity-connectors",
        "--benchmark-id",
        help="Benchmark directory name under --dataset-root.",
    ),
    dataset_root: Path = DATASET_ROOT_OPTION,
    hackerone_jsonl: Path | None = HACKERONE_JSONL_OPTION,
    line_index: list[int] = LINE_INDEX_OPTION,
    record_key: list[str] = RECORD_KEY_OPTION,
    max_records: int = typer.Option(
        200,
        "--max-records",
        min=1,
        max=5000,
        help="Maximum number of selected input records to process.",
    ),
    package_name: str = typer.Option(
        "web_exploit_skill_package_v1",
        "--package-name",
        help="Output skill package directory name under --output-root.",
    ),
    output_root: Path = SKILLS_OUTPUT_ROOT_OPTION,
    bootstrap_only: bool = typer.Option(
        False,
        "--bootstrap-only",
        help="Only create/repair base skills; skip record-driven edits.",
    ),
    model: str = typer.Option(
        "gpt-4.1-mini",
        "--model",
        help="OpenAI model used for classification and skill editing.",
    ),
    temperature: float = typer.Option(
        0.1,
        "--temperature",
        min=0.0,
        max=2.0,
        help="Sampling temperature for OpenAI completions.",
    ),
    disable_validation: bool = typer.Option(
        False,
        "--disable-validation",
        help="Disable local Agent Skills validator checks.",
    ),
    max_validation_attempts: int = typer.Option(
        3,
        "--max-validation-attempts",
        min=1,
        max=8,
        help="Maximum repair attempts after validator failures.",
    ),
) -> None:
    """Build a HackerOne-driven multi-skill package with bootstrap/full-flow modes."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print(
            "[red]OPENAI_API_KEY is not set.[/red] Add it to .env or src/.env before running."
        )
        raise typer.Exit(code=2)

    mode = SynthesisMode.BOOTSTRAP_ONLY if bootstrap_only else SynthesisMode.FULL
    try:
        run_hackerone_skill_package_pipeline(
            output_root=output_root,
            package_name=package_name,
            benchmark_id=benchmark_id,
            dataset_root=dataset_root,
            hackerone_jsonl_path=hackerone_jsonl,
            line_indices=line_index,
            record_keys=record_key,
            max_records=max_records,
            mode=mode,
            openai_api_key=api_key,
            openai_model=model,
            openai_temperature=temperature,
            validation_enabled=not disable_validation,
            max_validation_attempts=max_validation_attempts,
            console=console,
        )
    except Exception as exc:
        console.print(f"[red]Skill package build failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def main() -> None:
    """Run CLI app."""
    load_environment()
    app()


if __name__ == "__main__":
    main()
