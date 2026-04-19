from __future__ import annotations

import json

import httpx
import pytest

from skill_learner.connectors.base import ConnectorError
from skill_learner.connectors.config import HackerOneReportsJob
from skill_learner.connectors.hackerone_reports import HackerOneReportsConnector
from skill_learner.connectors.http import HTTPClient


def test_hackerone_connector_prefers_json_endpoint() -> None:
    report_payload = {
        "id": 291531,
        "title": "Introspection query leaks sensitive graphql system information.",
        "submitted_at": "2017-11-18T16:58:42.150Z",
        "vulnerability_information": (
            "Summary: test report\n"
            "Steps to reproduce:\n"
            "1. Send crafted graphql query"
        ),
        "cve_ids": ["CVE-2017-0001"],
    }

    html_payload = (
        "It looks like your JavaScript is disabled. "
        "To use HackerOne, enable JavaScript in your browser and refresh this page."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url_text = str(request.url)
        if url_text.endswith("/291531.json"):
            return httpx.Response(200, json=report_payload)
        if url_text.endswith("/291531"):
            return httpx.Response(200, text=html_payload)
        raise AssertionError(f"Unexpected URL: {url_text}")

    job = HackerOneReportsJob(
        source="hackerone_reports",
        report_ids=[291531],
        include_page_content=True,
        prefer_json_endpoint=True,
    )

    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = HackerOneReportsConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 1
    record = records[0]
    assert record.source_record_id == "291531"
    assert record.title == report_payload["title"]
    assert "JavaScript is disabled" not in (record.description or "")
    assert "crafted graphql query" in (record.description or "")
    assert "CVE-2017-0001" in record.cve_ids
    assert any(ref.kind == "report-json" for ref in record.references)


def test_hackerone_connector_skips_inaccessible_reports_when_others_succeed() -> None:
    report_payload = {
        "id": 291531,
        "title": "Accessible report",
        "submitted_at": "2017-11-18T16:58:42.150Z",
        "vulnerability_information": "Working JSON payload",
        "cve_ids": ["CVE-2017-0001"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url_text = str(request.url)
        if url_text.endswith("/291531.json"):
            return httpx.Response(200, json=report_payload)
        if url_text.endswith("/230244.json") or url_text.endswith("/230244"):
            return httpx.Response(403, text="forbidden")
        if url_text.endswith("/291531"):
            return httpx.Response(200, text="")
        raise AssertionError(f"Unexpected URL: {url_text}")

    job = HackerOneReportsJob(
        source="hackerone_reports",
        report_ids=[291531, 230244],
        include_page_content=True,
        prefer_json_endpoint=True,
    )

    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = HackerOneReportsConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 1
    assert records[0].source_record_id == "291531"


def test_hackerone_connector_raises_when_all_reports_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    job = HackerOneReportsJob(
        source="hackerone_reports",
        report_ids=[230244],
        include_page_content=True,
        prefer_json_endpoint=True,
    )

    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = HackerOneReportsConnector(job=job, http_client=http_client)
        with pytest.raises(ConnectorError):
            connector.fetch_records()


def test_hackerone_connector_discovers_report_ids_via_graphql() -> None:
    discovery_pages = {
        None: {
            "data": {
                "reports": {
                    "nodes": [{"_id": "1001"}, {"_id": "1002"}],
                    "pageInfo": {"endCursor": "MQ", "hasNextPage": True},
                }
            }
        },
        "MQ": {
            "data": {
                "reports": {
                    "nodes": [{"_id": "1003"}],
                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                }
            }
        },
    }

    report_payloads = {
        1001: {
            "id": 1001,
            "title": "Report one",
            "submitted_at": "2026-04-18T00:00:00Z",
            "vulnerability_information": "first",
        },
        1003: {
            "id": 1003,
            "title": "Report three",
            "submitted_at": "2026-04-18T00:00:00Z",
            "vulnerability_information": "third",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/graphql":
            payload = json.loads(request.content.decode("utf-8"))
            variables = payload.get("variables", {}) if isinstance(payload, dict) else {}
            after = variables.get("after") if isinstance(variables, dict) else None
            return httpx.Response(200, json=discovery_pages[after])

        if request.method == "GET" and request.url.path.startswith("/reports/"):
            report_id_text = request.url.path.split("/")[-1].replace(".json", "")
            report_id = int(report_id_text)
            if report_id == 1002:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=report_payloads[report_id])

        raise AssertionError(f"Unexpected URL: {request.method} {request.url}")

    job = HackerOneReportsJob(
        source="hackerone_reports",
        report_ids=[],
        discover_reports_via_graphql=True,
        discovery_page_size=2,
        include_page_content=False,
        prefer_json_endpoint=True,
    )

    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = HackerOneReportsConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert [record.source_record_id for record in records] == ["1001", "1003"]


def test_hackerone_connector_uses_static_ids_when_discovery_fails() -> None:
    static_payload = {
        "id": 291531,
        "title": "Static fallback report",
        "submitted_at": "2017-11-18T16:58:42.150Z",
        "vulnerability_information": "fallback",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/graphql":
            return httpx.Response(200, json={"errors": [{"message": "graphql unavailable"}]})
        if request.method == "GET" and request.url.path == "/reports/291531.json":
            return httpx.Response(200, json=static_payload)
        raise AssertionError(f"Unexpected URL: {request.method} {request.url}")

    job = HackerOneReportsJob(
        source="hackerone_reports",
        report_ids=[291531],
        discover_reports_via_graphql=True,
        include_page_content=False,
        prefer_json_endpoint=True,
    )

    with HTTPClient(transport=httpx.MockTransport(handler)) as http_client:
        connector = HackerOneReportsConnector(job=job, http_client=http_client)
        records = connector.fetch_records()

    assert len(records) == 1
    assert records[0].source_record_id == "291531"
