from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_learner.models import CybersecurityRecord, DataSource
from skill_learner.synthesis.cwe_catalog import WEB_VULNERABILITY_CATEGORIES
from skill_learner.synthesis.pipeline import (
    SkillPipelineError,
    infer_category_slug_from_record,
    load_hackerone_records,
    select_hackerone_records,
)


def _record(
    *,
    source: DataSource,
    source_record_id: str,
    title: str,
    description: str | None = None,
) -> CybersecurityRecord:
    return CybersecurityRecord(
        record_uid=f"{source.value}:{source_record_id}",
        source=source,
        source_record_id=source_record_id,
        title=title,
        description=description,
    )


def test_web_vulnerability_catalog_has_expected_breadth() -> None:
    assert 20 <= len(WEB_VULNERABILITY_CATEGORIES) <= 30
    assert WEB_VULNERABILITY_CATEGORIES[0].slug == "sql_injection"


def test_select_hackerone_records_by_line_and_key() -> None:
    records = [
        _record(source=DataSource.HACKERONE_REPORTS, source_record_id="1001", title="one"),
        _record(source=DataSource.HACKERONE_REPORTS, source_record_id="1002", title="two"),
        _record(source=DataSource.HACKERONE_REPORTS, source_record_id="1003", title="three"),
    ]

    selected = select_hackerone_records(
        records=records,
        line_indices=[2],
        record_keys=["1003"],
        max_records=10,
        allow_empty=False,
    )

    assert [item.source_record_id for item in selected] == ["1002", "1003"]
    assert [item.line_index_1_based for item in selected] == [2, 3]


def test_select_hackerone_records_requires_input_when_not_bootstrap_only() -> None:
    records = [
        _record(source=DataSource.HACKERONE_REPORTS, source_record_id="1001", title="one"),
    ]

    with pytest.raises(SkillPipelineError):
        select_hackerone_records(
            records=records,
            line_indices=[],
            record_keys=[],
            max_records=10,
            allow_empty=False,
        )


def test_load_hackerone_records_filters_other_sources(tmp_path: Path) -> None:
    hackerone_record = _record(
        source=DataSource.HACKERONE_REPORTS,
        source_record_id="2001",
        title="HackerOne report",
    )
    nvd_record = _record(
        source=DataSource.NVD,
        source_record_id="CVE-2026-0001",
        title="NVD record",
    )

    jsonl_path = tmp_path / "records.jsonl"
    lines = [
        json.dumps(hackerone_record.model_dump(mode="json"), sort_keys=True),
        json.dumps(nvd_record.model_dump(mode="json"), sort_keys=True),
    ]
    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records = load_hackerone_records(jsonl_path=jsonl_path)
    assert len(records) == 1
    assert records[0].source is DataSource.HACKERONE_REPORTS
    assert records[0].source_record_id == "2001"


def test_infer_category_slug_from_record_uses_trigger_hints() -> None:
    record = _record(
        source=DataSource.HACKERONE_REPORTS,
        source_record_id="3001",
        title="Potential SQL issue",
        description="Query error and UNION SELECT payload trigger SQL injection behavior.",
    )
    assert infer_category_slug_from_record(record) == "sql_injection"
