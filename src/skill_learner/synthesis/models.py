"""Typed contracts for web exploit skill package synthesis."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SynthesisMode(StrEnum):
    """Execution mode for skill package synthesis."""

    BOOTSTRAP_ONLY = "bootstrap_only"
    FULL = "full"


class TokenUsageSnapshot(BaseModel):
    """Token usage snapshot captured from one model call."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)


class RecordSelection(BaseModel):
    """One selected HackerOne record for synthesis input."""

    model_config = ConfigDict(extra="forbid")

    line_index_1_based: int = Field(ge=1)
    record_uid: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str | None = None


class SkillDecision(BaseModel):
    """LLM decision for which vulnerability skill to edit for one record."""

    model_config = ConfigDict(extra="forbid")

    vulnerability_skill_slug: str = Field(min_length=1)
    confidence: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    should_edit_general_observation: bool = True
    should_edit_vulnerability_skill: bool = True


class LLMTraceEntry(BaseModel):
    """Persisted trace for one model call to support debugging/research."""

    model_config = ConfigDict(extra="forbid")

    started_at_utc: datetime
    ended_at_utc: datetime
    step_type: str = Field(min_length=1)
    model: str = Field(min_length=1)
    record_uid: str | None = None
    target_skill_slug: str | None = None
    request_messages: list[dict[str, str]] = Field(default_factory=list)
    response_text: str = Field(default="")
    parsed_json: dict[str, Any] | None = None
    usage: TokenUsageSnapshot | None = None
    error: str | None = None

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def validate_utc_datetime(cls, value: datetime) -> datetime:
        """Require timezone-aware datetimes and normalize to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp values must be timezone-aware")
        return value.astimezone(UTC)


class SkillEditOutcome(BaseModel):
    """Outcome snapshot for one attempted skill update."""

    model_config = ConfigDict(extra="forbid")

    record_uid: str = Field(min_length=1)
    skill_slug: str = Field(min_length=1)
    validation_passed: bool
    validation_attempts: int = Field(ge=0)
    usage: TokenUsageSnapshot = Field(default_factory=TokenUsageSnapshot)


class SynthesisRunConfig(BaseModel):
    """Run configuration persisted with outputs for reproducibility."""

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(min_length=1)
    mode: SynthesisMode
    benchmark_id: str = Field(min_length=1)
    hackerone_jsonl_path: str = Field(min_length=1)
    line_indices: list[int] = Field(default_factory=list)
    record_keys: list[str] = Field(default_factory=list)
    max_records: int = Field(ge=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    validation_enabled: bool
    max_validation_attempts: int = Field(ge=1)
    bootstrap_missing_only: bool = True


class SynthesisRunSummary(BaseModel):
    """Top-level run summary persisted next to run traces."""

    model_config = ConfigDict(extra="forbid")

    started_at_utc: datetime
    ended_at_utc: datetime
    package_dir: str = Field(min_length=1)
    mode: SynthesisMode
    selected_records: int = Field(ge=0)
    bootstrap_created_skills: int = Field(ge=0)
    edited_skills: int = Field(ge=0)
    total_prompt_tokens: int = Field(ge=0)
    total_completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_cached_tokens: int = Field(ge=0)
    total_reasoning_tokens: int = Field(ge=0)
    traces_written: int = Field(ge=0)
    validation_failures: int = Field(ge=0)

    @field_validator("started_at_utc", "ended_at_utc")
    @classmethod
    def validate_utc_datetime(cls, value: datetime) -> datetime:
        """Require timezone-aware datetimes and normalize to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp values must be timezone-aware")
        return value.astimezone(UTC)
