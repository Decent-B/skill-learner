"""Command-line interface for the thesis pipeline."""

from __future__ import annotations

import platform
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from skill_learner import PACKAGE_NAME, __version__

app = typer.Typer(help="Skill extraction and evaluation pipeline.")
console = Console()


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


def main() -> None:
    """Run CLI app."""
    app()


if __name__ == "__main__":
    main()
