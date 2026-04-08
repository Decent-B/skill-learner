"""Unit tests for deterministic fingerprint helpers."""

from __future__ import annotations

from skill_learner.ingestion.fingerprint import build_source_id, sha256_bytes, sha256_text
from skill_learner.models import SourceType


def test_sha256_bytes_is_deterministic() -> None:
    digest1 = sha256_bytes(b"hello")
    digest2 = sha256_bytes(b"hello")
    assert digest1 == digest2
    assert len(digest1) == 64


def test_sha256_text_changes_when_input_changes() -> None:
    digest1 = sha256_text("hello")
    digest2 = sha256_text("hello!")
    assert digest1 != digest2


def test_build_source_id_is_stable_and_prefixed() -> None:
    source_id1 = build_source_id(
        source_type=SourceType.WEB,
        uri="https://example.com",
        content_sha256="a" * 64,
    )
    source_id2 = build_source_id(
        source_type=SourceType.WEB,
        uri="https://example.com",
        content_sha256="a" * 64,
    )
    assert source_id1 == source_id2
    assert source_id1.startswith("web_")
