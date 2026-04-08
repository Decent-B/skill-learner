"""Unit tests for ingestion orchestration and adapters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_learner.ingestion import SourceReadError, ingest_source
from skill_learner.models import SourceType


def test_ingest_text_source_writes_artifacts(tmp_path: Path) -> None:
    source_file = tmp_path / "sample.txt"
    source_file.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    raw_dir = tmp_path / "raw"
    manifests_dir = tmp_path / "manifests"

    record = ingest_source(
        source_type=SourceType.TEXT,
        path=source_file,
        raw_dir=raw_dir,
        manifest_dir=manifests_dir,
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert Path(record.storage_path).exists()
    assert Path(record.manifest_path).exists()

    manifest_payload = json.loads(Path(record.manifest_path).read_text(encoding="utf-8"))
    assert manifest_payload["source_id"] == record.source_id
    assert manifest_payload["metadata"]["source_type"] == "text"


def test_ingest_raises_on_missing_text_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.txt"

    with pytest.raises(SourceReadError):
        ingest_source(
            source_type=SourceType.TEXT,
            path=missing_file,
            raw_dir=tmp_path / "raw",
            manifest_dir=tmp_path / "manifests",
        )


def test_ingest_web_source_with_mocked_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_fetch_web_source(
        url: str,
        timeout_seconds: float = 15.0,
    ) -> tuple[str, dict[str, object]]:
        assert timeout_seconds == 15.0
        return (
            "Step 1: run mvn -B verify\nStep 2: check workflow logs.",
            {
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
            },
        )

    monkeypatch.setattr(
        "skill_learner.ingestion.ingest.fetch_web_source",
        fake_fetch_web_source,
    )

    record = ingest_source(
        source_type=SourceType.WEB,
        uri="https://example.com/build-doc",
        raw_dir=tmp_path / "raw",
        manifest_dir=tmp_path / "manifests",
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert record.metadata.source_type is SourceType.WEB
    assert "example.com" in record.metadata.uri
