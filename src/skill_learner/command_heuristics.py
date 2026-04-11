"""Shared heuristics for identifying shell command-like lines."""

from __future__ import annotations

import re

COMMAND_PREFIXES: tuple[str, ...] = (
    "mvn",
    "./mvnw",
    "gradle",
    "./gradlew",
    "bazel",
    "gh",
    "docker",
    "git",
    "java",
)

_PROSE_SECOND_TOKEN_BLOCKLIST = {
    "commands",
    "command",
    "includes",
    "include",
    "allows",
    "is",
    "will",
    "can",
    "also",
    "detects",
}
_PROSE_MARKERS = (
    "for more information",
    "invaluable aid",
    "used by two commands",
)
_SPACE_RE = re.compile(r"\s+")


def normalize_candidate_line(line: str) -> str:
    """Normalize whitespace and strip markdown code quoting wrappers."""
    return _SPACE_RE.sub(" ", line.strip().strip("`")).strip()


def is_command_like_line(line: str) -> bool:
    """
    Return True when the line looks like an executable shell command.

    The heuristic is intentionally conservative to avoid prose lines that happen
    to start with tool names (for example, "Gradle commands can include ...").
    """
    candidate = normalize_candidate_line(line)
    if not candidate:
        return False

    tokens = candidate.split()
    first = tokens[0]
    if first not in COMMAND_PREFIXES:
        return False

    # Prose in docs often starts with capitalized tool names ("Gradle ...").
    if first[0].isalpha() and first != first.lower():
        return False

    if len(tokens) < 2:
        return False
    if len(tokens) > 14:
        return False

    second = tokens[1].lower()
    if second in _PROSE_SECOND_TOKEN_BLOCKLIST:
        return False

    lowered = candidate.lower()
    if any(marker in lowered for marker in _PROSE_MARKERS):
        return False

    if candidate.endswith(":"):
        return False
    return True
