"""Canonical data contracts for connector ingestion and run metadata.

Connectors normalize source-specific payloads into these shared models before
the runner writes JSONL snapshots. Downstream normalization, evaluation, and
synthesis stages depend on these fields staying stable and well-documented.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataSource(StrEnum):
    """Canonical upstream sources for vulnerability and exploit intelligence."""

    NVD = "nvd"
    GITHUB_ADVISORIES = "github_advisories"
    NUCLEI_TEMPLATES = "nuclei_templates"
    EXPLOIT_DB = "exploit_db"
    PENTESTER_LAND = "pentester_land"
    HACKERONE_REPORTS = "hackerone_reports"


class SeverityMetric(BaseModel):
    """Normalized severity metric (CVSS, qualitative labels, etc.)."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = Field(
        min_length=1,
        description="Severity scheme name such as CVSS:3.1, GHSA, or NUCLEI.",
    )
    source: str | None = Field(
        default=None,
        description="System or organization that emitted this metric.",
    )
    vector: str | None = Field(
        default=None,
        description="Raw scoring vector when the upstream source provides one.",
    )
    score: float | None = Field(
        default=None,
        description="Numeric severity score in source-native scale.",
    )
    severity: str | None = Field(
        default=None,
        description="Qualitative label such as low, medium, high, or critical.",
    )


class AffectedTarget(BaseModel):
    """Normalized affected package/product target for a vulnerability."""

    model_config = ConfigDict(extra="forbid")

    ecosystem: str | None = Field(
        default=None,
        description="Package ecosystem identifier such as pypi, npm, or maven.",
    )
    package: str | None = Field(
        default=None,
        description="Affected package name when ecosystem-level data is available.",
    )
    vendor: str | None = Field(
        default=None,
        description="Vendor portion of affected software identity when known.",
    )
    product: str | None = Field(
        default=None,
        description="Product or service name impacted by the vulnerability.",
    )
    versions: list[str] = Field(
        default_factory=list,
        description="Version ranges or fixed-version markers tied to this target.",
    )
    cpe: str | None = Field(
        default=None,
        description="CPE 2.3 string when provided by the upstream source.",
    )


class Reference(BaseModel):
    """Reference URL with optional metadata."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        min_length=1,
        description="Absolute URL pointing to advisory, report, patch, or related evidence.",
    )
    kind: str | None = Field(
        default=None,
        description="Optional source-specific category, for example report-json or template.",
    )
    source: str | None = Field(
        default=None,
        description="Reference producer, usually matching connector source naming.",
    )


class ExploitArtifact(BaseModel):
    """Exploit or detection artifact linked to a record."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(
        min_length=1,
        description="Artifact category such as exploit-source, writeup-link, or nuclei-template.",
    )
    url: str = Field(
        min_length=1,
        description="Canonical location for downloading or inspecting this artifact.",
    )
    content: str | None = Field(
        default=None,
        description="Optional inline text body captured during ingestion for offline analysis.",
    )


class ProcedureEvidence(BaseModel):
    """Procedural extraction attached to one vulnerability/exploit record."""

    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(
        default_factory=list,
        description="Ordered attack or reproduction steps extracted from prose/list text.",
    )
    commands: list[str] = Field(
        default_factory=list,
        description="Command-line snippets inferred from free text and fenced code blocks.",
    )
    payloads: list[str] = Field(
        default_factory=list,
        description="Potential exploit payload fragments identified by heuristic patterns.",
    )


class CybersecurityRecord(BaseModel):
    """Canonical normalized record emitted by a connector."""

    model_config = ConfigDict(extra="forbid")

    record_uid: str = Field(
        min_length=3,
        description="Stable globally unique key in '<source>:<id>' style.",
    )
    source: DataSource = Field(description="Connector source that produced this normalized record.")
    source_record_id: str = Field(
        min_length=1,
        description="Original upstream identifier, for example CVE, GHSA, or report id.",
    )
    title: str = Field(
        min_length=1, description="Short title suitable for UI tables and summaries."
    )
    summary: str | None = Field(
        default=None,
        description="Optional concise abstract when distinct from full description.",
    )
    description: str | None = Field(
        default=None,
        description="Long-form textual context used by downstream extraction stages.",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="All known identifiers and aliases collected from source payloads.",
    )
    cve_ids: list[str] = Field(
        default_factory=list,
        description="Normalized CVE identifiers extracted or explicitly provided.",
    )
    ghsa_ids: list[str] = Field(
        default_factory=list,
        description="Normalized GHSA identifiers extracted or explicitly provided.",
    )
    cwe_ids: list[str] = Field(
        default_factory=list,
        description="Normalized CWE weakness identifiers referenced by the record.",
    )
    published_at_utc: datetime | None = Field(
        default=None,
        description="Publication timestamp normalized to timezone-aware UTC.",
    )
    modified_at_utc: datetime | None = Field(
        default=None,
        description="Last modification timestamp normalized to timezone-aware UTC.",
    )
    withdrawn_at_utc: datetime | None = Field(
        default=None,
        description="Withdrawal timestamp in UTC when an advisory/report was retracted.",
    )
    vuln_status: str | None = Field(
        default=None,
        description="Upstream status label such as verified, disclosed-report, or template.",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Human-readable weakness labels in addition to CWE identifiers.",
    )
    affected_targets: list[AffectedTarget] = Field(
        default_factory=list,
        description="Affected package/product targets derived from source metadata.",
    )
    severities: list[SeverityMetric] = Field(
        default_factory=list,
        description="Severity entries preserved from one or more scoring systems.",
    )
    epss_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="EPSS probability score in inclusive range [0, 1].",
    )
    epss_percentile: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="EPSS percentile in inclusive range [0, 1].",
    )
    references: list[Reference] = Field(
        default_factory=list,
        description="External links to advisories, reports, commits, or vendor notices.",
    )
    exploit_artifacts: list[ExploitArtifact] = Field(
        default_factory=list,
        description="Exploit-related artifacts (source code, template files, writeup excerpts).",
    )
    procedure: ProcedureEvidence = Field(
        default_factory=ProcedureEvidence,
        description="Heuristically extracted procedural evidence from textual content.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Connector-provided labels useful for quick filtering and faceting.",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-native payload fragments kept for traceability and debugging.",
    )

    @field_validator("published_at_utc", "modified_at_utc", "withdrawn_at_utc")
    @classmethod
    def validate_optional_utc_datetime(cls, value: datetime | None) -> datetime | None:
        """Require timezone-aware datetime values and normalize to UTC."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(UTC)


class RunStatus(StrEnum):
    """Execution status for one connector job."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConnectorRunSummary(BaseModel):
    """Snapshot metadata for one connector execution."""

    model_config = ConfigDict(extra="forbid")

    source: DataSource = Field(description="Connector source executed for this run entry.")
    status: RunStatus = Field(description="Terminal execution status for this connector job.")
    benchmark_id: str = Field(
        min_length=1,
        description="Benchmark or dataset identifier grouping related connector outputs.",
    )
    fetched_at_utc: datetime = Field(
        description="Run timestamp normalized to timezone-aware UTC.",
    )
    record_count: int = Field(
        ge=0,
        description="Number of normalized records written before completion/failure.",
    )
    output_path: str | None = Field(
        default=None,
        description="JSONL output path when records were persisted.",
    )
    metadata_path: str | None = Field(
        default=None,
        description="Metadata sidecar path storing this run summary.",
    )
    error: str | None = Field(
        default=None,
        description="Failure reason captured for failed runs, otherwise null.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized connector options snapshot for reproducibility.",
    )

    @field_validator("fetched_at_utc")
    @classmethod
    def validate_run_datetime(cls, value: datetime) -> datetime:
        """Require timezone-aware datetime values and normalize to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at_utc must be timezone-aware")
        return value.astimezone(UTC)
