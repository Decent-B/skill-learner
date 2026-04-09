"""Phase 2 pipeline runner for extraction preview artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skill_learner.extraction import extract_procedure
from skill_learner.ingestion import ingest_source_pack, write_batch_summary
from skill_learner.ingestion.batch import BatchIngestSummary, benchmark_report_stem
from skill_learner.normalization import load_manifest_record, normalize_manifest_record


def _build_preview_payload(
    summary: BatchIngestSummary,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "benchmark_id": summary.benchmark_id,
        "pack_path": summary.pack_path,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "totals": {
            "sources": summary.total_sources,
            "ingest_succeeded": summary.succeeded,
            "ingest_failed": summary.failed,
            "normalized": sum(1 for item in items if item.get("normalized_path") is not None),
            "extracted": sum(1 for item in items if item.get("steps") is not None),
        },
        "items": items,
    }


def _render_preview_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# fix-build-google-auto extraction preview")
    lines.append("")
    lines.append(f"- benchmark: `{payload['benchmark_id']}`")
    lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
    lines.append(
        f"- totals: sources={payload['totals']['sources']}, "
        f"ingest_succeeded={payload['totals']['ingest_succeeded']}, "
        f"ingest_failed={payload['totals']['ingest_failed']}, "
        f"normalized={payload['totals']['normalized']}, "
        f"extracted={payload['totals']['extracted']}"
    )
    lines.append("")
    lines.append("## Source results")
    lines.append("")

    for item in payload["items"]:
        lines.append(f"### {item['id']} ({item['status']})")
        lines.append("")
        if item.get("error"):
            lines.append(f"- failure: {item['error']}")
            lines.append("")
            continue

        lines.append(f"- source_id: `{item['source_id']}`")
        lines.append(f"- manifest_path: `{item['manifest_path']}`")
        lines.append(f"- normalized_path: `{item['normalized_path']}`")
        lines.append("- top commands:")
        commands: list[str] = item.get("command_candidates", [])
        if not commands:
            lines.append("  - (none)")
        else:
            for command in commands[:5]:
                lines.append(f"  - `{command}`")

        lines.append("- top procedural steps:")
        steps: list[dict[str, Any]] = item.get("steps", [])
        if not steps:
            lines.append("  - (none)")
        else:
            for step in steps[:5]:
                tag_text = ", ".join(step["tags"]) or "untagged"
                span = step.get("span")
                if isinstance(span, dict):
                    span_text = (
                        f"{span['section_title']}:{span['section_line_start']}"
                        f"-{span['section_line_end']}"
                    )
                else:
                    span_text = "unmapped"
                preconditions = "; ".join(step.get("preconditions", [])) or "none"
                postconditions = "; ".join(step.get("postconditions", [])) or "none"
                lines.append(
                    f"  - ({step['confidence']}) [{tag_text}] "
                    f"{step['text']}"
                )
                lines.append(f"    span: {span_text}")
                lines.append(f"    pre: {preconditions}")
                lines.append(f"    post: {postconditions}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def run_extract_preview(
    pack_path: Path,
    raw_dir: Path = Path("datasets/raw"),
    manifest_dir: Path = Path("datasets/manifests"),
    normalized_dir: Path = Path("datasets/normalized"),
    reports_dir: Path = Path("reports/runs"),
) -> tuple[Path, Path, Path]:
    """Execute the full Phase 2 preview flow and return output paths."""
    summary = ingest_source_pack(
        pack_path=pack_path,
        raw_dir=raw_dir,
        manifest_dir=manifest_dir,
    )
    stem = benchmark_report_stem(summary.benchmark_id)
    reports_dir.mkdir(parents=True, exist_ok=True)

    ingest_summary_path = (reports_dir / f"{stem}_ingest_summary.json").resolve()
    write_batch_summary(summary, summary_path=ingest_summary_path)

    preview_items: list[dict[str, Any]] = []
    for result in summary.results:
        item: dict[str, Any] = {
            "id": result.id,
            "source_type": result.source_type.value,
            "status": result.status,
            "url": result.url,
            "path": result.path,
            "source_id": result.source_id,
            "manifest_path": result.manifest_path,
            "raw_path": result.raw_path,
            "error": result.error,
        }

        if result.status == "success" and result.manifest_path is not None:
            try:
                manifest_record = load_manifest_record(Path(result.manifest_path))
                normalized, normalized_path = normalize_manifest_record(
                    manifest_record,
                    normalized_dir=normalized_dir,
                )
                extraction = extract_procedure(normalized)
            except (OSError, ValueError) as exc:
                item["status"] = "failed"
                item["error"] = str(exc)
            else:
                item["normalized_path"] = str(normalized_path)
                item["command_candidates"] = extraction.command_candidates
                item["steps"] = [step.model_dump(mode="json") for step in extraction.steps]

        preview_items.append(item)

    preview_payload = _build_preview_payload(summary=summary, items=preview_items)
    preview_json_path = (reports_dir / f"{stem}_step_preview.json").resolve()
    preview_markdown_path = (reports_dir / f"{stem}_step_preview.md").resolve()

    preview_json_path.write_text(
        json.dumps(preview_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    preview_markdown_path.write_text(_render_preview_markdown(preview_payload), encoding="utf-8")
    return ingest_summary_path, preview_json_path, preview_markdown_path
