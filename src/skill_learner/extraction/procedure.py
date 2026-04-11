"""Deterministic first-pass procedure extraction from normalized documents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from skill_learner.command_heuristics import is_command_like_line
from skill_learner.normalization.models import NormalizedDocument

from .models import ExtractedStep, ProcedureExtractionResult, SourceSpan, StepConfidence

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
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d+\.\s+)")
_WHITESPACE_RE = re.compile(r"\s+")
_ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_TECHNICAL_MARKERS = (
    "workflow",
    ".yml",
    ".yaml",
    "settings.xml",
    "pom.xml",
    "build.gradle",
    "java_home",
    "jdk",
    "maven",
    "gradle",
    "bazel",
    "dependency",
    "dependencies",
    "cache",
    "proxy",
    "mirror",
    "module",
    "artifact",
    "actions/",
    "--",
    "//",
    " -",
)


@dataclass
class _StepCandidate:
    text: str
    span: SourceSpan | None


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
    return is_command_like_line(text)


def _looks_imperative(text: str) -> bool:
    lower = text.strip().lower()
    return any(lower.startswith(f"{verb} ") for verb in _IMPERATIVE_VERBS)


def _is_numbered_step(text: str) -> bool:
    return _NUMBERED_STEP_RE.match(text.strip()) is not None


def _is_actionable_non_command_line(text: str) -> bool:
    """
    Return True for imperative/numbered lines with enough technical signal.

    This avoids generic prose such as "Use the tags" that is procedural in form
    but too abstract to be useful in executable skill synthesis.
    """
    compact = _WHITESPACE_RE.sub(" ", text.strip())
    if not compact or len(compact) > 220:
        return False

    word_count = len(compact.split())
    if word_count < 3:
        return False

    lower = compact.lower()
    if any(marker in lower for marker in _TECHNICAL_MARKERS):
        return True
    if "`" in compact:
        return True
    if _ENV_VAR_RE.search(compact):
        return True
    if any(token in lower for token in ("build", "test", "deploy", "verify", "rerun", "retry")):
        return True
    return False


def _normalize_for_span_match(text: str) -> str:
    compact = _WHITESPACE_RE.sub(" ", text.strip())
    without_prefix = _LIST_PREFIX_RE.sub("", compact)
    return without_prefix.strip().strip("`").lower()


def _build_span_index(normalized: NormalizedDocument) -> dict[str, SourceSpan]:
    index: dict[str, SourceSpan] = {}
    for section in normalized.sections:
        for section_line_number, raw_line in enumerate(section.body.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            key = _normalize_for_span_match(line)
            if not key or key in index:
                continue
            # Keep the first occurrence for deterministic provenance mapping.
            index[key] = SourceSpan(
                section_title=section.title,
                section_line_start=section_line_number,
                section_line_end=section_line_number,
            )
    return index


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


def _preconditions_for_step(text: str, tags: list[str]) -> list[str]:
    lower = text.strip().lower()
    preconditions: list[str] = []

    if _looks_like_command(text):
        if lower.startswith(("mvn ", "./mvnw ")):
            preconditions.append("Maven is available and the repository contains a valid pom.xml.")
        if lower.startswith(("gradle ", "./gradlew ")):
            preconditions.append(
                "Gradle is available and the repository contains a valid build configuration."
            )
        if lower.startswith("bazel "):
            preconditions.append("Bazel is installed and the workspace configuration is valid.")
        if lower.startswith("docker "):
            preconditions.append("Docker daemon access is available in the execution environment.")
        if lower.startswith("git "):
            preconditions.append("The command runs inside a valid Git repository checkout.")
        if lower.startswith("gh "):
            preconditions.append("GitHub CLI is authenticated for the target repository.")
        if lower.startswith("java "):
            preconditions.append("A compatible JDK is installed and JAVA_HOME is configured.")

    if "settings.xml" in lower:
        preconditions.append("Maven settings.xml is present or can be injected in CI.")
    if any(token in lower for token in ("workflow", ".yml", ".yaml", "actions/")):
        preconditions.append("The repository workflow file is editable.")
    if "dependency_fix" in tags:
        preconditions.append(
            "Repository credentials and network access for dependencies are configured."
        )
    return _dedupe_keep_order(preconditions)


def _postconditions_for_step(text: str, tags: list[str]) -> list[str]:
    lower = text.strip().lower()
    postconditions: list[str] = []

    if "build_cmd" in tags:
        postconditions.append("The command completes with exit code 0.")
    if any(token in lower for token in (" verify", " test", " build", " install", " check")):
        postconditions.append("Build or test execution finishes for the intended target.")
    if "dependency_fix" in tags:
        postconditions.append("Dependency resolution succeeds without missing artifacts.")
    if "ci_yaml" in tags:
        postconditions.append("Workflow configuration remains syntactically valid.")
    if "rerun_strategy" in tags:
        postconditions.append("Rerun starts from the targeted failing module or stage.")
    if "diagnostic_flag" in tags:
        postconditions.append("Logs contain expanded diagnostic information for debugging.")
    return _dedupe_keep_order(postconditions)


def _collect_step_candidates(normalized: NormalizedDocument) -> list[_StepCandidate]:
    span_index = _build_span_index(normalized)
    candidate_texts: list[str] = []
    candidate_texts.extend(normalized.command_like_lines)
    for item in normalized.list_items:
        # List items are noisy in scraped docs; only keep procedural entries.
        if _looks_like_command(item):
            candidate_texts.append(item)
            continue
        is_procedural = _is_numbered_step(item) or _looks_imperative(item)
        if is_procedural and _is_actionable_non_command_line(item):
            candidate_texts.append(item)

    for section in normalized.sections:
        for raw_line in section.body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _looks_like_command(line):
                candidate_texts.append(line)
                continue
            is_procedural = _is_numbered_step(line) or _looks_imperative(line)
            if is_procedural and _is_actionable_non_command_line(line):
                candidate_texts.append(line)

    deduped = _dedupe_keep_order(candidate_texts)
    candidates: list[_StepCandidate] = []
    for text in deduped:
        span = span_index.get(_normalize_for_span_match(text))
        candidates.append(_StepCandidate(text=text, span=span))
    return candidates


def extract_procedure(normalized: NormalizedDocument) -> ProcedureExtractionResult:
    """Extract deterministic step candidates, tags, and confidence labels."""
    step_candidates = _collect_step_candidates(normalized)
    steps: list[ExtractedStep] = []
    for candidate in step_candidates:
        tags = _tag_step(candidate.text)
        steps.append(
            ExtractedStep(
                source_id=normalized.source_id,
                text=candidate.text,
                tags=tags,
                span=candidate.span,
                preconditions=_preconditions_for_step(candidate.text, tags=tags),
                postconditions=_postconditions_for_step(candidate.text, tags=tags),
                confidence=_confidence_for_step(candidate.text, tags=tags),
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
