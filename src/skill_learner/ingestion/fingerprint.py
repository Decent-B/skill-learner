"""Deterministic fingerprint and source-id helpers for ingestion."""

from __future__ import annotations

from hashlib import sha256

from skill_learner.models import SourceType


def sha256_bytes(data: bytes) -> str:
    """Return lowercase SHA-256 digest for bytes."""
    return sha256(data).hexdigest()


def sha256_text(text: str, encoding: str = "utf-8") -> str:
    """Return lowercase SHA-256 digest for text."""
    return sha256_bytes(text.encode(encoding))


def build_source_id(source_type: SourceType, uri: str, content_sha256: str) -> str:
    """Build a deterministic, compact source identifier."""
    stable_key = f"{source_type.value}|{uri}|{content_sha256}"
    short_hash = sha256_text(stable_key)[:16]
    return f"{source_type.value}_{short_hash}"
