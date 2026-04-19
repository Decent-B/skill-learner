from __future__ import annotations

import httpx
import pytest

from skill_learner.connectors.config import GitHubAdvisoriesJob
from skill_learner.connectors.github_advisories import GitHubAdvisoriesConnector
from skill_learner.connectors.http import HTTPClient


def test_github_advisories_connector_follows_next_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")

    page_one = [
        {
            "ghsa_id": "GHSA-1111-2222-3333",
            "summary": "Issue one",
            "description": "A vulnerability with CVE-2026-1001.",
            "type": "reviewed",
            "severity": "high",
            "identifiers": [{"type": "GHSA", "value": "GHSA-1111-2222-3333"}],
            "references": ["https://example.test/1"],
            "vulnerabilities": [],
            "published_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
    ]
    page_two = [
        {
            "ghsa_id": "GHSA-4444-5555-6666",
            "summary": "Issue two",
            "description": "Second advisory",
            "type": "reviewed",
            "severity": "medium",
            "identifiers": [{"type": "GHSA", "value": "GHSA-4444-5555-6666"}],
            "references": ["https://example.test/2"],
            "vulnerabilities": [],
            "published_at": "2026-01-03T00:00:00Z",
            "updated_at": "2026-01-04T00:00:00Z",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer ghp_test_token"
        url_text = str(request.url)
        if "after=cursor2" in url_text:
            return httpx.Response(200, json=page_two)
        return httpx.Response(
            200,
            json=page_one,
            headers={
                "link": '<https://api.github.com/advisories?per_page=1&after=cursor2>; rel="next"'
            },
        )

    job = GitHubAdvisoriesJob(source="github_advisories", per_page=1, advisory_type="reviewed")
    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = GitHubAdvisoriesConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 2
    assert records[0].source_record_id == "GHSA-1111-2222-3333"
    assert records[1].source_record_id == "GHSA-4444-5555-6666"
