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
                        "mvn -X -B verify",
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
    assert by_text["mvn -X -B verify"].span is not None
    assert by_text["mvn -X -B verify"].span.section_title == "Repair flow"
    assert by_text["mvn -X -B verify"].span.section_line_start == 3
    assert by_text["mvn -X -B verify"].preconditions
    assert by_text["mvn -X -B verify"].postconditions

    rerun_step = by_text["rerun mvn -rf :module-a --also-make"]
    assert rerun_step.confidence is StepConfidence.MEDIUM
    assert "rerun_strategy" in rerun_step.tags
    assert rerun_step.span is not None
    assert rerun_step.span.section_line_start == 2
    assert rerun_step.postconditions

    dependency_step = by_text["Configure settings.xml mirror for dependencies"]
    assert dependency_step.confidence is StepConfidence.MEDIUM
    assert "dependency_fix" in dependency_step.tags
    assert dependency_step.span is not None
    assert dependency_step.span.section_line_start == 1
    assert dependency_step.preconditions


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


def test_extract_procedure_maps_numbered_list_item_to_source_span() -> None:
    normalized = NormalizedDocument(
        source_id="text_0101010101010101",
        source_uri="https://example.com/numbered",
        sections=[
            NormalizedSection(
                title="Flow",
                body="1. Configure workflow yaml\n2. Run mvn -B verify",
            )
        ],
        code_blocks=[],
        list_items=["Configure workflow yaml"],
        command_like_lines=[],
    )

    result = extract_procedure(normalized)
    by_text = {step.text: step for step in result.steps}

    step = by_text["Configure workflow yaml"]
    assert step.span is not None
    assert step.span.section_title == "Flow"
    assert step.span.section_line_start == 1


def test_extract_procedure_ignores_non_procedural_list_noise() -> None:
    normalized = NormalizedDocument(
        source_id="text_1111222233334444",
        source_uri="https://example.com/noise",
        sections=[NormalizedSection(title="Noise", body="created\nopened\nlabeled")],
        code_blocks=[],
        list_items=["created", "opened", "labeled"],
        command_like_lines=[],
    )

    result = extract_procedure(normalized)
    assert result.steps == []


def test_extract_procedure_filters_generic_imperative_without_technical_signal() -> None:
    normalized = NormalizedDocument(
        source_id="text_9999888877776666",
        source_uri="https://example.com/generic",
        sections=[NormalizedSection(title="Generic", body="Use the tags\nUse the paths")],
        code_blocks=[],
        list_items=["Use the tags", "Use the paths"],
        command_like_lines=[],
    )

    result = extract_procedure(normalized)
    assert result.steps == []
