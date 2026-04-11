"""Unit tests for synthesis writer selection and rendering."""

from __future__ import annotations

from skill_learner.extraction import StepConfidence
from skill_learner.synthesis.models import PreviewPayload, SkillMetadata
from skill_learner.synthesis.skill_writer import (
    render_skill_markdown,
    select_candidate_steps,
    suggest_skill_name,
)


def _preview_payload() -> PreviewPayload:
    return PreviewPayload.model_validate(
        {
            "benchmark_id": "fix-build-google-auto",
            "items": [
                {
                    "id": "G1",
                    "status": "success",
                    "steps": [
                        {
                            "source_id": "web_1111111111111111",
                            "text": "mvn -X -B verify",
                            "tags": ["build_cmd", "diagnostic_flag"],
                            "confidence": "high",
                            "span": {
                                "section_title": "Build flow",
                                "section_line_start": 12,
                                "section_line_end": 12,
                            },
                            "preconditions": ["Maven is available."],
                            "postconditions": ["The command completes with exit code 0."],
                        },
                        {
                            "source_id": "web_1111111111111111",
                            "text": "created",
                            "tags": [],
                            "confidence": "low",
                            "span": None,
                            "preconditions": [],
                            "postconditions": [],
                        },
                    ],
                },
                {
                    "id": "G2",
                    "status": "success",
                    "steps": [
                        {
                            "source_id": "web_2222222222222222",
                            "text": "rerun mvn -rf :core --also-make",
                            "tags": ["rerun_strategy"],
                            "confidence": "medium",
                            "span": None,
                            "preconditions": ["Repository checkout exists."],
                            "postconditions": ["Rerun starts from failing module."],
                        }
                    ],
                },
                {
                    "id": "G3",
                    "status": "failed",
                    "steps": None,
                },
            ],
        }
    )


def test_suggest_skill_name_is_spec_friendly() -> None:
    assert suggest_skill_name("fix-build-google-auto") == "fix-build-google-auto-repair"
    assert suggest_skill_name("Fix Build (Google) Auto") == "fix-build-google-auto-repair"


def test_select_candidate_steps_filters_noise_and_orders_by_priority() -> None:
    selected = select_candidate_steps(_preview_payload(), max_steps=10)
    assert len(selected) == 2
    assert selected[0].confidence is StepConfidence.HIGH
    assert selected[0].text == "mvn -X -B verify"
    assert selected[1].text == "rerun mvn -rf :core --also-make"


def test_select_candidate_steps_filters_placeholder_commands() -> None:
    payload = PreviewPayload.model_validate(
        {
            "benchmark_id": "fix-build-google-auto",
            "items": [
                {
                    "id": "G1",
                    "status": "success",
                    "steps": [
                        {
                            "source_id": "web_1111111111111111",
                            "text": "gradle [taskName...] [--option-name...]",
                            "tags": ["build_cmd"],
                            "confidence": "high",
                            "span": None,
                            "preconditions": [],
                            "postconditions": [],
                        },
                        {
                            "source_id": "web_1111111111111111",
                            "text": "gradle build --stacktrace",
                            "tags": ["build_cmd", "diagnostic_flag"],
                            "confidence": "high",
                            "span": None,
                            "preconditions": [],
                            "postconditions": [],
                        },
                    ],
                }
            ],
        }
    )

    selected = select_candidate_steps(payload, max_steps=10)
    assert [step.text for step in selected] == ["gradle build --stacktrace"]


def test_render_skill_markdown_contains_required_sections() -> None:
    selected = select_candidate_steps(_preview_payload(), max_steps=10)
    metadata = SkillMetadata(
        name="fix-build-google-auto-repair",
        description="Use this skill for CI build repair tasks.",
    )
    content = render_skill_markdown(metadata, selected)

    assert content.startswith("---\nname: fix-build-google-auto-repair\n")
    assert "## When To Use" in content
    assert "## Prerequisites" in content
    assert "## Build-Fix Procedure" in content
    assert "## Rerun And Verification" in content
    assert "## Failure Handling" in content
