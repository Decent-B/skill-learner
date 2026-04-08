"""Integration test for deterministic ingestion manifest I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from skill_learner.ingestion import ingest_source
from skill_learner.models import SourceType


def test_ingest_manifest_is_deterministic_for_fixed_input(tmp_path: Path) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_doc.txt"
    raw_dir = tmp_path / "raw"
    manifests_dir = tmp_path / "manifests"
    fixed_timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    first = ingest_source(
        source_type=SourceType.TEXT,
        path=fixture_path,
        raw_dir=raw_dir,
        manifest_dir=manifests_dir,
        fetched_at_utc=fixed_timestamp,
    )
    first_manifest = Path(first.manifest_path).read_text(encoding="utf-8")

    second = ingest_source(
        source_type=SourceType.TEXT,
        path=fixture_path,
        raw_dir=raw_dir,
        manifest_dir=manifests_dir,
        fetched_at_utc=fixed_timestamp,
    )
    second_manifest = Path(second.manifest_path).read_text(encoding="utf-8")

    assert first.source_id == second.source_id
    assert first.storage_path == second.storage_path
    assert first_manifest == second_manifest
