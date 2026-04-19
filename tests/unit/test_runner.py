from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_learner.connectors.config import ConnectorPack, NVDJob
from skill_learner.connectors.runner import collect_job, collect_pack
from skill_learner.models import ConnectorRunSummary, CybersecurityRecord, DataSource, RunStatus


def _record(source_record_id: str) -> CybersecurityRecord:
    return CybersecurityRecord(
        record_uid=f"nvd:{source_record_id}",
        source=DataSource.NVD,
        source_record_id=source_record_id,
        title=f"Record {source_record_id}",
    )


def test_collect_job_skips_disabled_job(tmp_path: Path) -> None:
    job = NVDJob(source="nvd", enabled=False)
    summary = collect_job(benchmark_id="demo", job=job, output_root=tmp_path)

    assert summary.source == DataSource.NVD
    assert summary.status == RunStatus.SKIPPED
    assert summary.record_count == 0


def test_collect_pack_runs_all_jobs(tmp_path: Path) -> None:
    pack = ConnectorPack(
        benchmark_id="demo",
        jobs=[
            NVDJob(source="nvd", enabled=False),
            NVDJob(source="nvd", enabled=False),
        ],
    )

    summaries = collect_pack(pack=pack, output_root=tmp_path)

    assert len(summaries) == 2
    assert all(summary.status == RunStatus.SKIPPED for summary in summaries)


def test_collect_pack_parallel_preserves_configured_job_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = ConnectorPack(
        benchmark_id="demo",
        max_concurrent_jobs=3,
        jobs=[
            NVDJob(source="nvd", max_records=1),
            NVDJob(source="nvd", max_records=2),
            NVDJob(source="nvd", max_records=3),
        ],
    )

    def fake_collect_job(benchmark_id: str, job: NVDJob, output_root: Path) -> ConnectorRunSummary:
        del output_root
        # Delays intentionally invert finish order so collect_pack must reorder summaries.
        time.sleep((4 - (job.max_records or 1)) * 0.01)
        return ConnectorRunSummary(
            source=DataSource.NVD,
            status=RunStatus.SUCCESS,
            benchmark_id=benchmark_id,
            fetched_at_utc=datetime.now(UTC),
            record_count=job.max_records or 0,
            output_path=None,
            metadata_path=None,
            error=None,
            options={},
        )

    monkeypatch.setattr("skill_learner.connectors.runner.collect_job", fake_collect_job)

    summaries = collect_pack(pack=pack, output_root=tmp_path)

    assert [summary.record_count for summary in summaries] == [1, 2, 3]


def test_collect_pack_parallel_converts_unexpected_worker_errors_to_failed_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = ConnectorPack(
        benchmark_id="demo",
        max_concurrent_jobs=2,
        jobs=[
            NVDJob(source="nvd", max_records=1),
            NVDJob(source="nvd", max_records=2),
        ],
    )

    def fake_collect_job(benchmark_id: str, job: NVDJob, output_root: Path) -> ConnectorRunSummary:
        del output_root
        if job.max_records == 2:
            raise RuntimeError("boom")
        return ConnectorRunSummary(
            source=DataSource.NVD,
            status=RunStatus.SUCCESS,
            benchmark_id=benchmark_id,
            fetched_at_utc=datetime.now(UTC),
            record_count=1,
            output_path=None,
            metadata_path=None,
            error=None,
            options={},
        )

    monkeypatch.setattr("skill_learner.connectors.runner.collect_job", fake_collect_job)

    summaries = collect_pack(pack=pack, output_root=tmp_path)

    assert summaries[0].status == RunStatus.SUCCESS
    assert summaries[1].status == RunStatus.FAILED
    assert summaries[1].error is not None
    assert "Unexpected runner failure" in summaries[1].error


def test_collect_job_preserves_partial_output_when_stream_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingConnector:
        def options_dict(self) -> dict[str, object]:
            return {"mode": "test"}

        def iter_records(self):
            yield _record("1")
            raise RuntimeError("stream boom")

    monkeypatch.setattr(
        "skill_learner.connectors.runner.create_connector",
        lambda job: FailingConnector(),
    )

    summary = collect_job(
        benchmark_id="demo",
        job=NVDJob(source="nvd", max_records=10),
        output_root=tmp_path,
        flush_every_records=1,
    )

    assert summary.status == RunStatus.FAILED
    assert summary.record_count == 1
    assert summary.output_path is not None
    assert summary.metadata_path is not None
    assert summary.error is not None

    output_path = Path(summary.output_path)
    output_lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(output_lines) == 1
    assert json.loads(output_lines[0])["source_record_id"] == "1"

    metadata = json.loads(Path(summary.metadata_path).read_text(encoding="utf-8"))
    assert metadata["status"] == RunStatus.FAILED.value
    assert metadata["record_count"] == 1


def test_collect_job_reports_live_progress_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StreamingConnector:
        def options_dict(self) -> dict[str, object]:
            return {}

        def iter_records(self):
            yield _record("1")
            yield _record("2")

    events: list[tuple[DataSource, str, int, str | None]] = []

    monkeypatch.setattr(
        "skill_learner.connectors.runner.create_connector",
        lambda job: StreamingConnector(),
    )

    summary = collect_job(
        benchmark_id="demo",
        job=NVDJob(source="nvd", max_records=10),
        output_root=tmp_path,
        progress_callback=lambda source, status, count, error: events.append(
            (source, status, count, error)
        ),
        flush_every_records=1,
        progress_every_records=1,
    )

    assert summary.status == RunStatus.SUCCESS
    assert events[0] == (DataSource.NVD, "running", 0, None)
    assert events[-1] == (DataSource.NVD, "success", 2, None)
    assert (DataSource.NVD, "running", 1, None) in events
    assert (DataSource.NVD, "running", 2, None) in events
