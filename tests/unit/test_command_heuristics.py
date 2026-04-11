"""Unit tests for shared command-line detection heuristics."""

from __future__ import annotations

from skill_learner.command_heuristics import is_command_like_line


def test_is_command_like_line_accepts_real_commands() -> None:
    assert is_command_like_line("mvn -X -B verify")
    assert is_command_like_line("./gradlew clean build")
    assert is_command_like_line("bazel build //google/example/library/v1:target")
    assert is_command_like_line("docker run --rm app:test")


def test_is_command_like_line_rejects_prose_like_lines() -> None:
    assert not is_command_like_line("Gradle commands can include various options.")
    assert not is_command_like_line("Bazel includes a query language for dependencies.")
    assert not is_command_like_line("git command allows inspection of files")
    assert not is_command_like_line("created")
