"""Normalization pipeline turning raw text into structured artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from skill_learner.models import ManifestRecord

from .models import NormalizedCodeBlock, NormalizedDocument, NormalizedSection

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCED_BLOCK_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_-]+)?\n(?P<body>.*?)```",
    flags=re.DOTALL,
)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)(?P<item>.+?)\s*$")
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


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _split_sections(text: str) -> list[NormalizedSection]:
    lines = text.splitlines()
    sections: list[NormalizedSection] = []
    current_title = "document"
    current_body: list[str] = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if match is not None:
            body = "\n".join(current_body).strip()
            if body:
                sections.append(NormalizedSection(title=current_title, body=body))
            current_title = match.group(2).strip()
            current_body = []
            continue
        current_body.append(line)

    tail_body = "\n".join(current_body).strip()
    if tail_body:
        sections.append(NormalizedSection(title=current_title, body=tail_body))
    if not sections:
        sections.append(NormalizedSection(title="document", body=text.strip() or " "))
    return sections


def _extract_code_blocks(text: str) -> list[NormalizedCodeBlock]:
    blocks: list[NormalizedCodeBlock] = []
    for match in _FENCED_BLOCK_RE.finditer(text):
        language = match.group("lang")
        body = match.group("body").strip()
        if not body:
            continue
        blocks.append(
            NormalizedCodeBlock(
                language=language.lower() if language else None,
                content=body,
            )
        )
    return blocks


def _extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        match = _LIST_ITEM_RE.match(line)
        if match is None:
            continue
        items.append(match.group("item").strip())
    return _dedupe_keep_order(items)


def _looks_like_command(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return any(lowered.startswith(prefix) for prefix in _COMMAND_PREFIXES)


def _extract_command_like_lines(text: str, code_blocks: list[NormalizedCodeBlock]) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        if _looks_like_command(line):
            candidates.append(line.strip())
    for block in code_blocks:
        for line in block.content.splitlines():
            if _looks_like_command(line):
                candidates.append(line.strip())
    return _dedupe_keep_order(candidates)


def normalize_text(source_id: str, source_uri: str, text: str) -> NormalizedDocument:
    """Create a normalized document structure from raw text."""
    code_blocks = _extract_code_blocks(text)
    return NormalizedDocument(
        source_id=source_id,
        source_uri=source_uri,
        sections=_split_sections(text),
        code_blocks=code_blocks,
        list_items=_extract_list_items(text),
        command_like_lines=_extract_command_like_lines(text, code_blocks=code_blocks),
    )


def write_normalized_document(document: NormalizedDocument, normalized_dir: Path) -> Path:
    """Persist a normalized document as deterministic JSON."""
    normalized_dir.mkdir(parents=True, exist_ok=True)
    out_path = (normalized_dir / f"{document.source_id}.json").resolve()
    payload = json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True)
    out_path.write_text(payload + "\n", encoding="utf-8")
    return out_path


def normalize_manifest_record(
    record: ManifestRecord,
    normalized_dir: Path = Path("datasets/normalized"),
) -> tuple[NormalizedDocument, Path]:
    """Read a manifest's raw text and persist normalized JSON."""
    raw_path = Path(record.storage_path)
    text = raw_path.read_text(encoding="utf-8")
    normalized = normalize_text(
        source_id=record.source_id,
        source_uri=record.metadata.uri,
        text=text,
    )
    output_path = write_normalized_document(normalized, normalized_dir=normalized_dir)
    return normalized, output_path


def load_manifest_record(manifest_path: Path) -> ManifestRecord:
    """Load one manifest record from JSON."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return ManifestRecord.model_validate(payload)
