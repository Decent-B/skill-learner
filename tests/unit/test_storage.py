"""Unit tests for ingestion storage helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_learner.ingestion.storage import (
    manifest_path_for,
    raw_text_path_for,
    write_manifest,
    write_raw_text,
)
from skill_learner.models import ManifestRecord, SourceMetadata, SourceType


def _build_manifest_record(tmp_path: Path) -> ManifestRecord:
    metadata = SourceMetadata(
        source_id="text_abcd1234abcd1234",
        source_type=SourceType.TEXT,
        uri=str((tmp_path / "sample.txt").resolve()),
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        content_sha256="a" * 64,
        byte_size=12,
        mime_type="text/plain",
    )
    return ManifestRecord(
        source_id=metadata.source_id,
        storage_path=str((tmp_path / "raw" / "text_abcd1234abcd1234.txt").resolve()),
        manifest_path=str((tmp_path / "manifests" / "text_abcd1234abcd1234.json").resolve()),
        metadata=metadata,
    )


def test_write_raw_text_and_manifest(tmp_path: Path) -> None:
    record = _build_manifest_record(tmp_path=tmp_path)
    raw_dir = tmp_path / "raw"
    manifest_dir = tmp_path / "manifests"

    raw_path = write_raw_text(source_id=record.source_id, text="hello", raw_dir=raw_dir)
    manifest_path = write_manifest(record=record, manifest_dir=manifest_dir)

    assert raw_path.read_text(encoding="utf-8") == "hello"
    assert manifest_path.read_text(encoding="utf-8").strip().startswith("{")


def test_storage_rejects_invalid_source_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        raw_text_path_for(source_id="../bad", raw_dir=tmp_path / "raw")
    with pytest.raises(ValueError):
        manifest_path_for(source_id="../bad", manifest_dir=tmp_path / "manifests")
