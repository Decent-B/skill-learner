"""Unit tests for normalization stage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from skill_learner.models import ManifestRecord, SourceMetadata, SourceType
from skill_learner.normalization import normalize_manifest_record, normalize_text


def test_normalize_text_extracts_sections_lists_code_and_commands() -> None:
    text = "\n".join(
        [
            "# Build workflow",
            "1. Run mvn -B verify",
            "- Configure cache",
            "",
            "```bash",
            "mvn -X -B verify",
            "docker run --rm app:test",
            "```",
        ]
    )

    normalized = normalize_text(
        source_id="text_1234567890abcdef",
        source_uri="file:///tmp/sample.txt",
        text=text,
    )

    assert normalized.sections[0].title == "Build workflow"
    assert "Configure cache" in normalized.list_items
    assert len(normalized.code_blocks) == 1
    assert "mvn -X -B verify" in normalized.command_like_lines
    assert "docker run --rm app:test" in normalized.command_like_lines


def test_normalize_manifest_record_writes_json(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw" / "text_aaaaaaaaaaaaaaaa.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("gradle build --stacktrace\n", encoding="utf-8")

    metadata = SourceMetadata(
        source_id="text_aaaaaaaaaaaaaaaa",
        source_type=SourceType.TEXT,
        uri=str(raw_path),
        fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        content_sha256="a" * 64,
        byte_size=raw_path.stat().st_size,
        mime_type="text/plain",
        adapter_metadata={},
    )
    record = ManifestRecord(
        source_id=metadata.source_id,
        storage_path=str(raw_path),
        manifest_path=str(tmp_path / "manifests" / "dummy.json"),
        metadata=metadata,
    )

    normalized, output_path = normalize_manifest_record(
        record=record,
        normalized_dir=tmp_path / "normalized",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert normalized.source_id == "text_aaaaaaaaaaaaaaaa"
    assert payload["source_id"] == "text_aaaaaaaaaaaaaaaa"
    assert payload["command_like_lines"] == ["gradle build --stacktrace"]
