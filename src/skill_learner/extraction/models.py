"""Typed models for extracted procedural knowledge."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StepConfidence(StrEnum):
    """Confidence levels for first-pass deterministic extraction."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractedStep(BaseModel):
    """One extracted procedural step."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    confidence: StepConfidence


class ProcedureExtractionResult(BaseModel):
    """Extraction output for one normalized source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    source_uri: str = Field(min_length=1)
    command_candidates: list[str]
    steps: list[ExtractedStep]
