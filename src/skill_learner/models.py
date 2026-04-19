"""Typed contracts for web-cybersecurity connector ingestion."""

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

    scheme: str = Field(min_length=1)
    source: str | None = None
    vector: str | None = None
    score: float | None = None
    severity: str | None = None


class AffectedTarget(BaseModel):
    """Normalized affected package/product target for a vulnerability."""

    model_config = ConfigDict(extra="forbid")

    ecosystem: str | None = None
    package: str | None = None
    vendor: str | None = None
    product: str | None = None
    versions: list[str] = Field(default_factory=list)
    cpe: str | None = None


class Reference(BaseModel):
    """Reference URL with optional metadata."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    kind: str | None = None
    source: str | None = None


class ExploitArtifact(BaseModel):
    """Exploit or detection artifact linked to a record."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    url: str = Field(min_length=1)
    content: str | None = None


class ProcedureEvidence(BaseModel):
    """Procedural extraction attached to one vulnerability/exploit record."""

    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    payloads: list[str] = Field(default_factory=list)


class CybersecurityRecord(BaseModel):
    """Canonical normalized record emitted by a connector."""

    model_config = ConfigDict(extra="forbid")

    record_uid: str = Field(min_length=3)
    source: DataSource
    source_record_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str | None = None
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    cve_ids: list[str] = Field(default_factory=list)
    ghsa_ids: list[str] = Field(default_factory=list)
    cwe_ids: list[str] = Field(default_factory=list)
    published_at_utc: datetime | None = None
    modified_at_utc: datetime | None = None
    withdrawn_at_utc: datetime | None = None
    vuln_status: str | None = None
    weaknesses: list[str] = Field(default_factory=list)
    affected_targets: list[AffectedTarget] = Field(default_factory=list)
    severities: list[SeverityMetric] = Field(default_factory=list)
    epss_score: float | None = Field(default=None, ge=0.0, le=1.0)
    epss_percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    references: list[Reference] = Field(default_factory=list)
    exploit_artifacts: list[ExploitArtifact] = Field(default_factory=list)
    procedure: ProcedureEvidence = Field(default_factory=ProcedureEvidence)
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

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

    source: DataSource
    status: RunStatus
    benchmark_id: str = Field(min_length=1)
    fetched_at_utc: datetime
    record_count: int = Field(ge=0)
    output_path: str | None = None
    metadata_path: str | None = None
    error: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fetched_at_utc")
    @classmethod
    def validate_run_datetime(cls, value: datetime) -> datetime:
        """Require timezone-aware datetime values and normalize to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at_utc must be timezone-aware")
        return value.astimezone(UTC)
