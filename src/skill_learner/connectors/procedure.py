"""Procedure and payload extraction helpers for connector records."""

from __future__ import annotations

import re

from skill_learner.models import ProcedureEvidence

_COMMAND_PREFIXES = (
    "curl",
    "wget",
    "python",
    "python3",
    "node",
    "npm",
    "pip",
    "go",
    "ruby",
    "bash",
    "sh",
    "sqlmap",
    "nuclei",
    "nmap",
    "ffuf",
    "gobuster",
    "msfconsole",
    "msfvenom",
    "git",
    "docker",
    "kubectl",
    "aws",
)

_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)(.+)\s*$")
_CODE_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\n(.*?)```", flags=re.DOTALL)
_SPACE_RE = re.compile(r"\s+")

_PAYLOAD_PATTERNS = (
    re.compile(r"<script[^>]*>.*?</script>", flags=re.IGNORECASE | re.DOTALL),
    re.compile(r"\bUNION\s+SELECT\b", flags=re.IGNORECASE),
    re.compile(r"\bOR\s+1\s*=\s*1\b", flags=re.IGNORECASE),
    re.compile(r"\.\./"),
    re.compile(r"%2e%2e", flags=re.IGNORECASE),
    re.compile(r"\$\{jndi:[^}]+\}", flags=re.IGNORECASE),
    re.compile(r"onerror\s*=", flags=re.IGNORECASE),
    re.compile(r"\bselect\b.+\bfrom\b", flags=re.IGNORECASE),
)


def _normalize_line(line: str) -> str:
    return _SPACE_RE.sub(" ", line.strip().strip("`"))


def _looks_command_like(line: str) -> bool:
    if not line:
        return False
    tokens = line.split()
    if len(tokens) < 2 or len(tokens) > 50:
        return False
    first = tokens[0].lower()
    return first in _COMMAND_PREFIXES


def extract_procedure_evidence(text: str) -> ProcedureEvidence:
    """Extract step, command, and payload candidates from free text."""
    steps: list[str] = []
    commands: list[str] = []
    payloads: list[str] = []

    for raw_line in text.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue

        list_match = _LIST_LINE_RE.match(raw_line)
        if list_match is not None:
            candidate = _normalize_line(list_match.group(1))
            if len(candidate) >= 8:
                steps.append(candidate)

        if _looks_command_like(line):
            commands.append(line)

        for pattern in _PAYLOAD_PATTERNS:
            for match in pattern.finditer(raw_line):
                payload = _normalize_line(match.group(0))
                if payload:
                    payloads.append(payload)

    for code_block in _CODE_FENCE_RE.findall(text):
        for raw_line in code_block.splitlines():
            line = _normalize_line(raw_line)
            if _looks_command_like(line):
                commands.append(line)

    return ProcedureEvidence(
        steps=_dedupe(steps),
        commands=_dedupe(commands),
        payloads=_dedupe(payloads),
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
