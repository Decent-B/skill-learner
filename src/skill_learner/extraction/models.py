"""Typed models for extracted procedural knowledge."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StepConfidence(StrEnum):
    """Confidence levels for first-pass deterministic extraction."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceSpan(BaseModel):
    """Reference to where the step was found in normalized source text."""

    model_config = ConfigDict(extra="forbid")

    section_title: str = Field(min_length=1)
    section_line_start: int = Field(ge=1)
    section_line_end: int = Field(ge=1)


class ExtractedStep(BaseModel):
    """One extracted procedural step."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    span: SourceSpan | None = None
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    confidence: StepConfidence


class ProcedureExtractionResult(BaseModel):
    """Extraction output for one normalized source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    source_uri: str = Field(min_length=1)
    command_candidates: list[str]
    steps: list[ExtractedStep]
