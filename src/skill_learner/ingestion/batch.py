"""Batch ingestion runner for benchmark source packs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from skill_learner.models import SourceType

from .ingest import ingest_source
from .sources import IngestionError

_SAFE_NAME_RE = re.compile(r"[^a-z0-9]+")


class PackSource(BaseModel):
    """One ingestion target from a benchmark source pack."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    source_type: SourceType
    url: str | None = None
    path: str | None = None
    quality: str | None = None
    expected_skill_ops: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_location(self) -> PackSource:
        """Require URL for web and file path for local source types."""
        if self.source_type is SourceType.WEB:
            if self.url is None or self.path is not None:
                raise ValueError("web sources require `url` and forbid `path`")
            return self

        if self.path is None or self.url is not None:
            raise ValueError("pdf/text sources require `path` and forbid `url`")
        return self


class SourcePack(BaseModel):
    """Typed representation of a benchmark source pack YAML."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str = Field(min_length=1)
    task: str | None = None
    generated_on: str | None = None
    sources: list[PackSource] = Field(min_length=1)


class BatchIngestItemResult(BaseModel):
    """Result for one source item inside a batch ingestion run."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: SourceType
    status: str = Field(pattern=r"^(success|failed)$")
    url: str | None = None
    path: str | None = None
    source_id: str | None = None
    manifest_path: str | None = None
    raw_path: str | None = None
    error: str | None = None


class BatchIngestSummary(BaseModel):
    """Serializable summary for one pack ingestion run."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    pack_path: str
    run_started_at_utc: datetime
    total_sources: int
    succeeded: int
    failed: int
    results: list[BatchIngestItemResult]


def load_source_pack(pack_path: Path) -> SourcePack:
    """Load and validate a YAML source pack."""
    try:
        payload = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read source pack: {pack_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"source pack must be a mapping: {pack_path}")
    return SourcePack.model_validate(payload)


def benchmark_report_stem(benchmark_id: str) -> str:
    """Return a filesystem-safe report stem from benchmark_id."""
    lower = benchmark_id.strip().lower()
    normalized = _SAFE_NAME_RE.sub("_", lower).strip("_")
    if not normalized:
        raise ValueError("benchmark_id cannot be empty")
    return normalized


def write_batch_summary(summary: BatchIngestSummary, summary_path: Path) -> Path:
    """Persist a deterministic JSON summary for a batch run."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True)
    summary_path.write_text(content + "\n", encoding="utf-8")
    return summary_path


def ingest_source_pack(
    pack_path: Path,
    raw_dir: Path = Path("datasets/raw"),
    manifest_dir: Path = Path("datasets/manifests"),
    run_started_at_utc: datetime | None = None,
) -> BatchIngestSummary:
    """Ingest every source declared in a source pack and keep per-item status."""
    pack = load_source_pack(pack_path)
    started_at = run_started_at_utc or datetime.now(UTC)

    results: list[BatchIngestItemResult] = []
    succeeded = 0
    for source in pack.sources:
        try:
            record = ingest_source(
                source_type=source.source_type,
                uri=source.url,
                path=Path(source.path) if source.path is not None else None,
                raw_dir=raw_dir,
                manifest_dir=manifest_dir,
            )
        except (IngestionError, ValueError) as exc:
            results.append(
                BatchIngestItemResult(
                    id=source.id,
                    source_type=source.source_type,
                    status="failed",
                    url=source.url,
                    path=source.path,
                    error=str(exc),
                )
            )
            continue

        succeeded += 1
        results.append(
            BatchIngestItemResult(
                id=source.id,
                source_type=source.source_type,
                status="success",
                url=source.url,
                path=source.path,
                source_id=record.source_id,
                manifest_path=record.manifest_path,
                raw_path=record.storage_path,
            )
        )

    failed = len(pack.sources) - succeeded
    return BatchIngestSummary(
        benchmark_id=pack.benchmark_id,
        pack_path=str(pack_path.resolve()),
        run_started_at_utc=started_at,
        total_sources=len(pack.sources),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )
