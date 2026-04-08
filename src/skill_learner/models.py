"""Typed contracts shared by ingestion and downstream pipeline phases."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceType(StrEnum):
    """Supported ingestion source types."""

    WEB = "web"
    PDF = "pdf"
    TEXT = "text"


class SourceMetadata(BaseModel):
    """Canonical metadata for ingested source documents."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    source_type: SourceType
    uri: str = Field(min_length=1)
    fetched_at_utc: datetime
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=0)
    mime_type: str | None = None
    adapter_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fetched_at_utc")
    @classmethod
    def validate_utc_datetime(cls, value: datetime) -> datetime:
        """Require timezone-aware datetimes and normalize to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at_utc must be timezone-aware")
        return value.astimezone(UTC)


class RawDocument(BaseModel):
    """In-memory representation of extracted source text + metadata."""

    model_config = ConfigDict(extra="forbid")

    metadata: SourceMetadata
    raw_text: str = Field(min_length=1)


class ManifestRecord(BaseModel):
    """Manifest persisted after an ingestion run."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    storage_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    metadata: SourceMetadata
