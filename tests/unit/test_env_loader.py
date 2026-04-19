from __future__ import annotations

import os
from pathlib import Path

import pytest

from skill_learner.env import load_environment


def test_load_environment_reads_export_and_quoted_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / "sample.env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "NVD_API_KEY=abc123",
                "export GITHUB_TOKEN='ghp_example'",
                'QUOTED="value with spaces"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("NVD_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)

    loaded = load_environment(paths=[env_path])

    assert loaded == (env_path.resolve(),)
    assert os.environ.get("NVD_API_KEY") == "abc123"
    assert os.environ.get("GITHUB_TOKEN") == "ghp_example"
    assert os.environ.get("QUOTED") == "value with spaces"


def test_load_environment_override_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / "sample.env"
    env_path.write_text("NVD_API_KEY=from_file\n", encoding="utf-8")

    monkeypatch.setenv("NVD_API_KEY", "already_set")

    load_environment(paths=[env_path], override=False)
    assert os.environ.get("NVD_API_KEY") == "already_set"

    load_environment(paths=[env_path], override=True)
    assert os.environ.get("NVD_API_KEY") == "from_file"
