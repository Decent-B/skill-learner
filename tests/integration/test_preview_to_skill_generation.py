"""Integration tests for preview -> generated skill synthesis."""

from __future__ import annotations

import json
from pathlib import Path

from skill_learner.synthesis import synthesize_skill_from_preview


def test_preview_to_skill_generation(tmp_path: Path) -> None:
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
                                "span": {
                                    "section_title": "Build flow",
                                    "section_line_start": 10,
                                    "section_line_end": 10,
                                },
                                "preconditions": ["Maven is available."],
                                "postconditions": ["The command completes with exit code 0."],
                            },
                            {
                                "source_id": "web_aaaaaaaaaaaaaaaa",
                                "text": "update settings.xml mirror for dependencies",
                                "tags": ["dependency_fix"],
                                "confidence": "medium",
                                "span": {
                                    "section_title": "Dependency flow",
                                    "section_line_start": 4,
                                    "section_line_end": 4,
                                },
                                "preconditions": ["Repository credentials are configured."],
                                "postconditions": ["Dependency resolution succeeds."],
                            },
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

    skill_md = Path(result.skill_md_path).read_text(encoding="utf-8")
    reference = Path(result.reference_path).read_text(encoding="utf-8")

    assert result.selected_step_count == 2
    assert "name: fix-build-google-auto-repair" in skill_md
    assert "## Build-Fix Procedure" in skill_md
    assert "mvn -X -B verify" in skill_md
    assert "source_item_id" in reference
    assert "Build flow:10-10" in reference
