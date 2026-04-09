"""Unit tests for procedure extraction heuristics."""

from __future__ import annotations

from skill_learner.extraction import StepConfidence, extract_procedure
from skill_learner.normalization.models import NormalizedDocument, NormalizedSection


def test_extract_procedure_adds_tags_and_confidence() -> None:
    normalized = NormalizedDocument(
        source_id="text_1234567890abcdef",
        source_uri="https://example.com/build-fix",
        sections=[
            NormalizedSection(
                title="Repair flow",
                body="\n".join(
                    [
                        "1. Configure settings.xml mirror for dependencies",
                        "rerun mvn -rf :module-a --also-make",
                    ]
                ),
            )
        ],
        code_blocks=[],
        list_items=["Configure settings.xml mirror for dependencies"],
        command_like_lines=["mvn -X -B verify", "git checkout -b fix-build"],
    )

    result = extract_procedure(normalized)
    by_text = {step.text: step for step in result.steps}

    assert "mvn -X -B verify" in result.command_candidates
    assert by_text["mvn -X -B verify"].confidence is StepConfidence.HIGH
    assert "build_cmd" in by_text["mvn -X -B verify"].tags
    assert "diagnostic_flag" in by_text["mvn -X -B verify"].tags

    rerun_step = by_text["rerun mvn -rf :module-a --also-make"]
    assert rerun_step.confidence is StepConfidence.MEDIUM
    assert "rerun_strategy" in rerun_step.tags

    dependency_step = by_text["Configure settings.xml mirror for dependencies"]
    assert dependency_step.confidence is StepConfidence.MEDIUM
    assert "dependency_fix" in dependency_step.tags


def test_extract_procedure_handles_untagged_text_as_low_confidence() -> None:
    normalized = NormalizedDocument(
        source_id="text_abcdefabcdefabcd",
        source_uri="https://example.com/notes",
        sections=[NormalizedSection(title="Notes", body="remember this")],
        code_blocks=[],
        list_items=[],
        command_like_lines=[],
    )

    result = extract_procedure(normalized)

    assert result.steps == []
