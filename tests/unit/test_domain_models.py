from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skill_learner.models import CybersecurityRecord, DataSource


def _minimal_record_payload() -> dict[str, object]:
    return {
        "record_uid": "nvd:CVE-2026-9999",
        "source": DataSource.NVD,
        "source_record_id": "CVE-2026-9999",
        "title": "Example vulnerability",
        "published_at_utc": datetime.now(UTC),
    }


def test_cybersecurity_record_accepts_timezone_aware_datetime() -> None:
    record = CybersecurityRecord.model_validate(_minimal_record_payload())
    assert record.published_at_utc is not None
    assert record.published_at_utc.tzinfo is not None


def test_cybersecurity_record_rejects_naive_datetime() -> None:
    payload = _minimal_record_payload()
    payload["published_at_utc"] = datetime.now()

    with pytest.raises(ValidationError):
        CybersecurityRecord.model_validate(payload)
