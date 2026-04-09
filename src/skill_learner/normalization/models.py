"""Typed models for normalized document artifacts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NormalizedSection(BaseModel):
    """A semantic section split from raw text."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    body: str = Field(min_length=1)


class NormalizedCodeBlock(BaseModel):
    """A fenced code block extracted from source text."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = None
    content: str = Field(min_length=1)


class NormalizedDocument(BaseModel):
    """Normalized representation used by extraction stages."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_]+$")
    source_uri: str = Field(min_length=1)
    sections: list[NormalizedSection]
    code_blocks: list[NormalizedCodeBlock]
    list_items: list[str]
    command_like_lines: list[str]
