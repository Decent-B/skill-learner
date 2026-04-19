from __future__ import annotations

import httpx
import pytest

from skill_learner.connectors.config import NVDJob
from skill_learner.connectors.http import HTTPClient
from skill_learner.connectors.nvd import NVDConnector


def test_nvd_connector_parses_one_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVD_API_KEY", "nvd-test-api-key")

    payload = {
        "resultsPerPage": 1,
        "startIndex": 0,
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-1111",
                    "published": "2026-01-01T00:00:00.000",
                    "lastModified": "2026-01-02T00:00:00.000",
                    "vulnStatus": "Analyzed",
                    "descriptions": [{"lang": "en", "value": "Buffer overflow in parser."}],
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "source": "nvd@nist.gov",
                                "baseSeverity": "HIGH",
                                "cvssData": {
                                    "version": "3.1",
                                    "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                                    "baseScore": 9.8,
                                },
                            }
                        ]
                    },
                    "weaknesses": [
                        {
                            "description": [
                                {
                                    "lang": "en",
                                    "value": "CWE-120",
                                }
                            ]
                        }
                    ],
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "cpeMatch": [
                                        {
                                            "criteria": (
                                                "cpe:2.3:a:vendor:product:"
                                                "1.2.3:*:*:*:*:*:*:*"
                                            )
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                    "references": [{"url": "https://example.test/advisory", "source": "example"}],
                }
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://services.nvd.nist.gov/rest/json/cves/2.0")
        assert request.headers.get("apiKey") == "nvd-test-api-key"
        return httpx.Response(200, json=payload)

    job = NVDJob(source="nvd", max_records=1)
    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = NVDConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 1
    record = records[0]
    assert record.source_record_id == "CVE-2026-1111"
    assert record.cve_ids == ["CVE-2026-1111"]
    assert record.cwe_ids == ["CWE-120"]
    assert record.affected_targets[0].product == "product"
    assert record.severities[0].score == 9.8


def test_nvd_connector_falls_back_to_cve_id_when_description_yields_empty_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVD_API_KEY", "nvd-test-api-key")

    payload = {
        "resultsPerPage": 1,
        "startIndex": 0,
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-2222",
                    "published": "2026-01-01T00:00:00.000",
                    "lastModified": "2026-01-02T00:00:00.000",
                    "vulnStatus": "Analyzed",
                    "descriptions": [{"lang": "en", "value": ". malformed summary"}],
                    "metrics": {},
                    "weaknesses": [],
                    "configurations": [],
                    "references": [],
                }
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://services.nvd.nist.gov/rest/json/cves/2.0")
        assert request.headers.get("apiKey") == "nvd-test-api-key"
        return httpx.Response(200, json=payload)

    job = NVDJob(source="nvd", max_records=1)
    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = NVDConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 1
    assert records[0].title == "CVE-2026-2222"
