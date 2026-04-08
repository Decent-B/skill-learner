"""Orchestration entrypoint for ingesting source documents."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_learner.models import ManifestRecord, SourceMetadata, SourceType

from .fingerprint import build_source_id, sha256_text
from .sources import fetch_web_source, read_pdf_source, read_text_source
from .storage import manifest_path_for, raw_text_path_for, write_manifest, write_raw_text


def _validate_input_combo(source_type: SourceType, uri: str | None, path: Path | None) -> None:
    if source_type is SourceType.WEB:
        if uri is None or path is not None:
            raise ValueError("web ingestion requires --uri and forbids --path")
        return

    if source_type in {SourceType.PDF, SourceType.TEXT}:
        if path is None or uri is not None:
            raise ValueError("pdf/text ingestion requires --path and forbids --uri")
        return

    raise ValueError(f"unsupported source_type: {source_type}")


def _read_source(
    source_type: SourceType,
    uri: str | None,
    path: Path | None,
) -> tuple[str, str, str | None, dict[str, Any]]:
    if source_type is SourceType.WEB:
        assert uri is not None  # Validated by _validate_input_combo.
        text, adapter_metadata = fetch_web_source(uri)
        content_type = adapter_metadata.get("content_type")
        mime_type = str(content_type) if content_type is not None else None
        return text, uri, mime_type, adapter_metadata

    assert path is not None  # Validated by _validate_input_combo.
    resolved_path = path.resolve()
    if source_type is SourceType.PDF:
        text, adapter_metadata = read_pdf_source(resolved_path)
        return text, str(resolved_path), "application/pdf", adapter_metadata

    text, adapter_metadata = read_text_source(resolved_path)
    return text, str(resolved_path), "text/plain", adapter_metadata


def ingest_source(
    source_type: SourceType,
    uri: str | None = None,
    path: Path | None = None,
    raw_dir: Path = Path("datasets/raw"),
    manifest_dir: Path = Path("datasets/manifests"),
    fetched_at_utc: datetime | None = None,
) -> ManifestRecord:
    """Ingest one source and persist raw text + manifest artifacts."""
    _validate_input_combo(source_type=source_type, uri=uri, path=path)

    text, canonical_uri, mime_type, adapter_metadata = _read_source(
        source_type=source_type,
        uri=uri,
        path=path,
    )

    content_sha256 = sha256_text(text)
    source_id = build_source_id(
        source_type=source_type,
        uri=canonical_uri,
        content_sha256=content_sha256,
    )
    timestamp = fetched_at_utc or datetime.now(UTC)

    raw_path = raw_text_path_for(source_id=source_id, raw_dir=raw_dir)
    manifest_path = manifest_path_for(source_id=source_id, manifest_dir=manifest_dir)

    metadata = SourceMetadata(
        source_id=source_id,
        source_type=source_type,
        uri=canonical_uri,
        fetched_at_utc=timestamp,
        content_sha256=content_sha256,
        byte_size=len(text.encode("utf-8")),
        mime_type=mime_type,
        adapter_metadata=adapter_metadata,
    )
    record = ManifestRecord(
        source_id=source_id,
        storage_path=str(raw_path),
        manifest_path=str(manifest_path),
        metadata=metadata,
    )

    write_raw_text(source_id=source_id, text=text, raw_dir=raw_dir)
    write_manifest(record=record, manifest_dir=manifest_dir)
    return record
