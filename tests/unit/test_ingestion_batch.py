"""Unit tests for benchmark pack batch ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_learner.ingestion.batch import (
    benchmark_report_stem,
    ingest_source_pack,
    load_source_pack,
    write_batch_summary,
)
from skill_learner.ingestion.sources import IngestionError
from skill_learner.models import ManifestRecord, SourceMetadata, SourceType


def _write_pack(pack_path: Path) -> None:
    pack_path.write_text(
        "\n".join(
            [
                "benchmark_id: fix-build-google-auto",
                "sources:",
                "  - id: G1",
                "    source_type: web",
                "    url: https://example.com/doc-1",
                "  - id: G2",
                "    source_type: web",
                "    url: https://example.com/doc-2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_source_pack_valid_yaml(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack.yaml"
    _write_pack(pack_path)

    pack = load_source_pack(pack_path)

    assert pack.benchmark_id == "fix-build-google-auto"
    assert len(pack.sources) == 2
    assert pack.sources[0].source_type is SourceType.WEB


def test_ingest_source_pack_continues_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pack_path = tmp_path / "pack.yaml"
    _write_pack(pack_path)

    def fake_ingest_source(
        source_type: SourceType,
        uri: str | None = None,
        path: Path | None = None,
        raw_dir: Path = Path("datasets/raw"),
        manifest_dir: Path = Path("datasets/manifests"),
        fetched_at_utc: datetime | None = None,
    ) -> ManifestRecord:
        del path, raw_dir, manifest_dir, fetched_at_utc
        if uri == "https://example.com/doc-2":
            raise IngestionError("boom")
        assert source_type is SourceType.WEB
        metadata = SourceMetadata(
            source_id="web_1111111111111111",
            source_type=SourceType.WEB,
            uri=uri or "",
            fetched_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            content_sha256="1" * 64,
            byte_size=123,
            mime_type="text/html",
            adapter_metadata={},
        )
        return ManifestRecord(
            source_id=metadata.source_id,
            storage_path="/tmp/raw.txt",
            manifest_path="/tmp/manifest.json",
            metadata=metadata,
        )

    monkeypatch.setattr("skill_learner.ingestion.batch.ingest_source", fake_ingest_source)

    summary = ingest_source_pack(
        pack_path=pack_path,
        raw_dir=tmp_path / "raw",
        manifest_dir=tmp_path / "manifests",
    )

    assert summary.total_sources == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.results[0].status == "success"
    assert summary.results[1].status == "failed"
    assert summary.results[1].error == "boom"


def test_write_batch_summary_json(tmp_path: Path) -> None:
    local_source = tmp_path / "source.txt"
    local_source.write_text("run mvn -B verify\n", encoding="utf-8")
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "\n".join(
            [
                "benchmark_id: fix-build-google-auto",
                "sources:",
                "  - id: L1",
                "    source_type: text",
                f"    path: {local_source}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary = ingest_source_pack(
        pack_path=pack_path,
        raw_dir=tmp_path / "raw",
        manifest_dir=tmp_path / "m",
    )
    output_path = tmp_path / "reports" / "summary.json"

    written = write_batch_summary(summary, summary_path=output_path)

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["benchmark_id"] == "fix-build-google-auto"
    assert payload["total_sources"] == 1


def test_benchmark_report_stem() -> None:
    assert benchmark_report_stem("fix-build-google-auto") == "fix_build_google_auto"
