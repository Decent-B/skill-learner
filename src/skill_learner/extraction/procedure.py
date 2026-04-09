"""Deterministic first-pass procedure extraction from normalized documents."""

from __future__ import annotations

import json
import re
from pathlib import Path

from skill_learner.normalization.models import NormalizedDocument

from .models import ExtractedStep, ProcedureExtractionResult, StepConfidence

_COMMAND_PREFIXES = (
    "mvn ",
    "./mvnw ",
    "gradle ",
    "./gradlew ",
    "bazel ",
    "gh ",
    "docker ",
    "git ",
    "java ",
)
_NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+.+")
_IMPERATIVE_VERBS = (
    "run",
    "set",
    "add",
    "update",
    "configure",
    "use",
    "rerun",
    "retry",
    "check",
    "inspect",
    "verify",
    "install",
    "build",
    "test",
    "execute",
)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        stripped = item.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        ordered.append(stripped)
    return ordered


def _looks_like_command(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(prefix) for prefix in _COMMAND_PREFIXES)


def _looks_imperative(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(f"{verb} ") for verb in _IMPERATIVE_VERBS)


def _is_numbered_step(text: str) -> bool:
    return _NUMBERED_STEP_RE.match(text.strip()) is not None


def _tag_step(text: str) -> list[str]:
    lower = text.lower()
    tags: list[str] = []

    if _looks_like_command(text):
        tags.append("build_cmd")
    if any(token in lower for token in ("workflow", ".yml", ".yaml", "actions/")):
        tags.append("ci_yaml")
    if any(
        token in lower
        for token in (
            "dependency",
            "dependencies",
            "settings.xml",
            "mirror",
            "proxy",
            "repository",
            "artifact",
        )
    ):
        tags.append("dependency_fix")
    if any(
        token in lower
        for token in ("rerun", "retry", "resume from", "--rerun", "--rerun-tasks", " -rf ")
    ):
        tags.append("rerun_strategy")
    if any(
        token in lower
        for token in ("-x", "-e", "--stacktrace", "--debug", "--info", "diagnos", "trace", "log")
    ):
        tags.append("diagnostic_flag")
    return _dedupe_keep_order(tags)


def _confidence_for_step(text: str, tags: list[str]) -> StepConfidence:
    if _looks_like_command(text):
        return StepConfidence.HIGH
    if _is_numbered_step(text) or _looks_imperative(text):
        return StepConfidence.MEDIUM
    if tags:
        return StepConfidence.MEDIUM
    return StepConfidence.LOW


def _collect_step_candidates(normalized: NormalizedDocument) -> list[str]:
    candidates: list[str] = []
    candidates.extend(normalized.command_like_lines)
    candidates.extend(normalized.list_items)

    for section in normalized.sections:
        for raw_line in section.body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _is_numbered_step(line) or _looks_imperative(line) or _looks_like_command(line):
                candidates.append(line)
    return _dedupe_keep_order(candidates)


def extract_procedure(normalized: NormalizedDocument) -> ProcedureExtractionResult:
    """Extract deterministic step candidates, tags, and confidence labels."""
    step_candidates = _collect_step_candidates(normalized)
    steps: list[ExtractedStep] = []
    for candidate in step_candidates:
        tags = _tag_step(candidate)
        steps.append(
            ExtractedStep(
                source_id=normalized.source_id,
                text=candidate,
                tags=tags,
                confidence=_confidence_for_step(candidate, tags=tags),
            )
        )

    return ProcedureExtractionResult(
        source_id=normalized.source_id,
        source_uri=normalized.source_uri,
        command_candidates=_dedupe_keep_order(normalized.command_like_lines),
        steps=steps,
    )


def load_normalized_document(path: Path) -> NormalizedDocument:
    """Load one normalized document from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return NormalizedDocument.model_validate(payload)
