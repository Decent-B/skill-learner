"""Environment variable loading utilities for CLI workflows."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED_ENV_FILES: tuple[Path, ...] | None = None


def load_environment(
    *,
    paths: list[Path] | None = None,
    override: bool = False,
) -> tuple[Path, ...]:
    """Load .env files into process environment.

    By default we look for `.env` and `src/.env` from the current working
    directory, plus `src/.env` near the installed package. Existing non-empty
    environment variables are preserved unless `override=True`.
    """
    global _LOADED_ENV_FILES

    if paths is None and not override and _LOADED_ENV_FILES is not None:
        return _LOADED_ENV_FILES

    target_paths = _default_env_paths() if paths is None else list(paths)
    loaded: list[Path] = []

    for env_path in target_paths:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            current = os.environ.get(key)
            if override or current is None or current == "":
                os.environ[key] = value
        loaded.append(env_path.resolve())

    loaded_tuple = tuple(loaded)
    if paths is None and not override:
        _LOADED_ENV_FILES = loaded_tuple
    return loaded_tuple


def _default_env_paths() -> list[Path]:
    cwd = Path.cwd()
    package_src = Path(__file__).resolve().parents[1]
    candidates = [
        cwd / ".env",
        cwd / "src" / ".env",
        package_src / ".env",
    ]

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        value = value[1:-1]
    return key, value
