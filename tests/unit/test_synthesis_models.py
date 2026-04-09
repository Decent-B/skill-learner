"""Unit tests for synthesis model contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_learner.synthesis.models import SkillMetadata


def test_skill_metadata_accepts_valid_name_and_description() -> None:
    metadata = SkillMetadata(
        name="fix-build-google-auto-repair",
        description="Use when fixing CI build failures in Java repositories.",
    )
    assert metadata.name == "fix-build-google-auto-repair"


@pytest.mark.parametrize(
    "invalid_name",
    [
        "Fix-Build",  # uppercase
        "-skill",  # starts with hyphen
        "skill-",  # ends with hyphen
        "skill--repair",  # consecutive hyphens
        "skill_name",  # underscore
    ],
)
def test_skill_metadata_rejects_invalid_name(invalid_name: str) -> None:
    with pytest.raises(ValidationError):
        SkillMetadata(
            name=invalid_name,
            description="Use when fixing builds.",
        )


def test_skill_metadata_rejects_overlong_description() -> None:
    with pytest.raises(ValidationError):
        SkillMetadata(
            name="valid-skill",
            description="a" * 1025,
        )
