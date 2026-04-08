"""Unit tests for package import behavior."""

from __future__ import annotations

import skill_learner


def test_package_metadata_exports() -> None:
    assert skill_learner.PACKAGE_NAME == "skill-learner"
    assert isinstance(skill_learner.__version__, str)
    assert len(skill_learner.__version__) > 0
