"""Integration tests for generated skill validation via agentskills CLI."""

from __future__ import annotations

import json
from pathlib import Path

from skill_learner.synthesis import synthesize_skill_from_preview, validate_skill_directory


def test_generated_skill_passes_agentskills_validation(tmp_path: Path) -> None:
    preview_path = tmp_path / "preview.json"
    preview_path.write_text(
        json.dumps(
            {
                "benchmark_id": "fix-build-google-auto",
                "items": [
                    {
                        "id": "G1",
                        "status": "success",
                        "steps": [
                            {
                                "source_id": "web_aaaaaaaaaaaaaaaa",
                                "text": "mvn -X -B verify",
                                "tags": ["build_cmd", "diagnostic_flag"],
                                "confidence": "high",
                                "span": None,
                                "preconditions": ["Maven is available."],
                                "postconditions": ["The command completes with exit code 0."],
                            }
                        ],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = synthesize_skill_from_preview(
        preview_json=preview_path,
        output_root=tmp_path / "skills",
        skill_name="fix-build-google-auto-repair",
        validate=False,
    )

    ok, output = validate_skill_directory(Path(result.skill_dir))
    assert ok is True
    assert output is not None


def test_invalid_skill_directory_fails_validation(tmp_path: Path) -> None:
    bad_skill = tmp_path / "bad-skill"
    bad_skill.mkdir(parents=True, exist_ok=True)
    # Invalid due to uppercase name and mismatch with parent directory.
    (bad_skill / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: BadSkill",
                "description: bad",
                "---",
                "",
                "content",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ok, output = validate_skill_directory(bad_skill)
    assert ok is False
    assert output
