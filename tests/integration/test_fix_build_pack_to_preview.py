"""Integration tests for end-to-end Phase 2 preview generation."""

from __future__ import annotations

import json
from pathlib import Path

from skill_learner.pipeline import run_extract_preview


def test_fix_build_pack_to_preview_outputs_expected_artifacts(tmp_path: Path) -> None:
    source_ok = tmp_path / "doc_ok.txt"
    source_ok.write_text(
        "\n".join(
            [
                "# CI fix",
                "1. Run mvn -X -B verify",
                "- Update settings.xml mirror",
                "mvn -rf :module-a --also-make",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    source_missing = tmp_path / "doc_missing.txt"
    pack_path = tmp_path / "pack.yaml"
    pack_path.write_text(
        "\n".join(
            [
                "benchmark_id: fix-build-google-auto",
                "sources:",
                "  - id: L1",
                "    source_type: text",
                f"    path: {source_ok}",
                "  - id: L2",
                "    source_type: text",
                f"    path: {source_missing}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ingest_summary_path, preview_json_path, preview_markdown_path = run_extract_preview(
        pack_path=pack_path,
        raw_dir=tmp_path / "raw",
        manifest_dir=tmp_path / "manifests",
        normalized_dir=tmp_path / "normalized",
        reports_dir=tmp_path / "reports",
    )

    assert ingest_summary_path.exists()
    assert preview_json_path.exists()
    assert preview_markdown_path.exists()

    payload = json.loads(preview_json_path.read_text(encoding="utf-8"))
    assert payload["totals"]["sources"] == 2
    assert payload["totals"]["ingest_succeeded"] == 1
    assert payload["totals"]["ingest_failed"] == 1
    assert payload["totals"]["normalized"] == 1
    assert payload["totals"]["extracted"] == 1

    success_item = next(item for item in payload["items"] if item["id"] == "L1")
    failed_item = next(item for item in payload["items"] if item["id"] == "L2")

    assert success_item["status"] == "success"
    assert "mvn -rf :module-a --also-make" in success_item["command_candidates"]
    assert len(success_item["steps"]) > 0

    assert failed_item["status"] == "failed"
    assert failed_item["error"] is not None
