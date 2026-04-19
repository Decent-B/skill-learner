"""Execution runner for connector jobs and packs."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from skill_learner.models import ConnectorRunSummary, DataSource, RunStatus

from .config import ConnectorJob, ConnectorPack, load_connector_pack, source_name
from .registry import create_connector

ProgressCallback = Callable[[DataSource, str, int, str | None], None]


def _write_metadata(summary: ConnectorRunSummary, metadata_path: Path) -> None:
    metadata_path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _emit_progress(
    progress_callback: ProgressCallback | None,
    source: DataSource,
    status: str,
    record_count: int,
    error: str | None,
) -> None:
    if progress_callback is not None:
        progress_callback(source, status, record_count, error)


def collect_job(
    benchmark_id: str,
    job: ConnectorJob,
    output_root: Path,
    *,
    progress_callback: ProgressCallback | None = None,
    flush_every_records: int = 1,
    progress_every_records: int = 25,
) -> ConnectorRunSummary:
    """Execute one connector job and persist records + metadata snapshots."""
    source = source_name(job)
    fetched_at = datetime.now(UTC)

    if not job.enabled:
        _emit_progress(progress_callback, source, "skipped", 0, None)
        return ConnectorRunSummary(
            source=source,
            status=RunStatus.SKIPPED,
            benchmark_id=benchmark_id,
            fetched_at_utc=fetched_at,
            record_count=0,
            output_path=None,
            metadata_path=None,
            error=None,
            options={},
        )

    try:
        connector = create_connector(job)
    except Exception as exc:
        _emit_progress(progress_callback, source, "failed", 0, str(exc))
        return ConnectorRunSummary(
            source=source,
            status=RunStatus.FAILED,
            benchmark_id=benchmark_id,
            fetched_at_utc=fetched_at,
            record_count=0,
            output_path=None,
            metadata_path=None,
            error=str(exc),
            options={},
        )

    options = connector.options_dict()

    run_dir = output_root / benchmark_id / source.value
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")

    output_path = (run_dir / f"{timestamp}.jsonl").resolve()
    metadata_path = (run_dir / f"{timestamp}.meta.json").resolve()

    record_count = 0
    flush_interval = max(1, flush_every_records)
    progress_interval = max(1, progress_every_records)
    _emit_progress(progress_callback, source, "running", record_count, None)

    try:
        with output_path.open("w", encoding="utf-8") as handle:
            for record in connector.iter_records():
                handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n")
                record_count += 1
                if record_count % flush_interval == 0:
                    handle.flush()
                if record_count % progress_interval == 0:
                    _emit_progress(progress_callback, source, "running", record_count, None)
            handle.flush()
    except Exception as exc:
        summary = ConnectorRunSummary(
            source=source,
            status=RunStatus.FAILED,
            benchmark_id=benchmark_id,
            fetched_at_utc=fetched_at,
            record_count=record_count,
            output_path=str(output_path),
            metadata_path=str(metadata_path),
            error=str(exc),
            options=options,
        )
        _write_metadata(summary, metadata_path)
        _emit_progress(progress_callback, source, "failed", record_count, str(exc))
        return summary

    summary = ConnectorRunSummary(
        source=source,
        status=RunStatus.SUCCESS,
        benchmark_id=benchmark_id,
        fetched_at_utc=fetched_at,
        record_count=record_count,
        output_path=str(output_path),
        metadata_path=str(metadata_path),
        error=None,
        options=options,
    )

    _write_metadata(summary, metadata_path)
    _emit_progress(progress_callback, source, "success", record_count, None)
    return summary


def collect_pack(
    pack: ConnectorPack,
    output_root: Path,
    *,
    max_concurrent_jobs: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[ConnectorRunSummary]:
    """Execute every connector job in a validated connector pack."""
    configured_workers = (
        max_concurrent_jobs if max_concurrent_jobs is not None else pack.max_concurrent_jobs
    )
    worker_count = max(1, min(configured_workers, len(pack.jobs)))

    if worker_count == 1:
        if progress_callback is None:
            return [
                collect_job(benchmark_id=pack.benchmark_id, job=job, output_root=output_root)
                for job in pack.jobs
            ]
        return [
            collect_job(
                benchmark_id=pack.benchmark_id,
                job=job,
                output_root=output_root,
                progress_callback=progress_callback,
            )
            for job in pack.jobs
        ]

    summaries_by_index: dict[int, ConnectorRunSummary] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        if progress_callback is None:
            futures = {
                executor.submit(
                    collect_job,
                    benchmark_id=pack.benchmark_id,
                    job=job,
                    output_root=output_root,
                ): index
                for index, job in enumerate(pack.jobs)
            }
        else:
            futures = {
                executor.submit(
                    collect_job,
                    benchmark_id=pack.benchmark_id,
                    job=job,
                    output_root=output_root,
                    progress_callback=progress_callback,
                ): index
                for index, job in enumerate(pack.jobs)
            }

        for future in as_completed(futures):
            index = futures[future]
            try:
                summaries_by_index[index] = future.result()
            except Exception as exc:
                failed_job = pack.jobs[index]
                summaries_by_index[index] = ConnectorRunSummary(
                    source=source_name(failed_job),
                    status=RunStatus.FAILED,
                    benchmark_id=pack.benchmark_id,
                    fetched_at_utc=datetime.now(UTC),
                    record_count=0,
                    output_path=None,
                    metadata_path=None,
                    error=f"Unexpected runner failure: {exc}",
                    options={},
                )
                _emit_progress(
                    progress_callback,
                    source_name(failed_job),
                    "failed",
                    0,
                    str(exc),
                )

    return [summaries_by_index[index] for index in range(len(pack.jobs))]


def collect_pack_from_file(
    pack_path: Path,
    output_root: Path,
    *,
    max_concurrent_jobs: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[ConnectorPack, list[ConnectorRunSummary]]:
    """Load a connector pack file and execute all configured jobs."""
    pack = load_connector_pack(pack_path)
    return pack, collect_pack(
        pack=pack,
        output_root=output_root,
        max_concurrent_jobs=max_concurrent_jobs,
        progress_callback=progress_callback,
    )
