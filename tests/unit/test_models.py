"""Unit tests for typed ingestion data contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skill_learner.models import ManifestRecord, SourceMetadata, SourceType


def test_source_metadata_accepts_valid_payload() -> None:
    metadata = SourceMetadata(
        source_id="text_abcd1234abcd1234",
        source_type=SourceType.TEXT,
        uri="/tmp/sample.txt",
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        content_sha256="a" * 64,
        byte_size=42,
        mime_type="text/plain",
        adapter_metadata={"encoding": "utf-8"},
    )
    assert metadata.source_type is SourceType.TEXT
    assert metadata.byte_size == 42


def test_source_metadata_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        SourceMetadata(
            source_id="text_abcd1234abcd1234",
            source_type=SourceType.TEXT,
            uri="/tmp/sample.txt",
            fetched_at_utc=datetime(2026, 1, 1),
            content_sha256="a" * 64,
            byte_size=1,
        )


def test_source_metadata_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        SourceMetadata(
            source_id="text_abcd1234abcd1234",
            source_type=SourceType.TEXT,
            uri="/tmp/sample.txt",
            fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            content_sha256="not-a-sha256",
            byte_size=1,
        )


def test_manifest_record_serializes() -> None:
    metadata = SourceMetadata(
        source_id="text_abcd1234abcd1234",
        source_type=SourceType.TEXT,
        uri="/tmp/sample.txt",
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        content_sha256="a" * 64,
        byte_size=5,
    )
    manifest = ManifestRecord(
        source_id=metadata.source_id,
        storage_path="datasets/raw/text_abcd1234abcd1234.txt",
        manifest_path="datasets/manifests/text_abcd1234abcd1234.json",
        metadata=metadata,
    )
    dumped = manifest.model_dump(mode="json")
    assert dumped["source_id"] == "text_abcd1234abcd1234"
