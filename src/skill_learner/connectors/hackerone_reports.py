"""Connector for disclosed HackerOne report pages by explicit report ID."""

from __future__ import annotations

import re
from collections.abc import Iterator

import trafilatura

from skill_learner.models import (
    AffectedTarget,
    CybersecurityRecord,
    DataSource,
    ExploitArtifact,
    Reference,
    SeverityMetric,
)

from .base import BaseConnector, ConnectorError
from .config import HackerOneReportsJob
from .http import HTTPClient
from .procedure import extract_procedure_evidence
from .utils import extract_cve_ids, parse_datetime_utc, unique_str

_REPORT_TITLE_RE = re.compile(r"#\d+\s+(.+)")
_PUBLISHED_RE = re.compile(
    (
        r"submitted a report.*?"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}(?:am|pm)\s+UTC)"
    ),
    re.IGNORECASE,
)
_REPORT_DISCOVERY_QUERY = """
query DiscoverPublicReports($first: Int!, $after: String) {
    reports(
        first: $first
        after: $after
        order_by: { field: submitted_at, direction: DESC }
    ) {
        pageInfo {
            endCursor
            hasNextPage
        }
        nodes {
            _id
        }
    }
}
"""


class HackerOneReportsConnector(BaseConnector):
    """Fetch and normalize HackerOne disclosed reports from known report IDs."""

    source = DataSource.HACKERONE_REPORTS

    def __init__(self, job: HackerOneReportsJob, http_client: HTTPClient | None = None) -> None:
        self._job = job
        self._http = http_client or HTTPClient()
        self._owns_http = http_client is None

    def __del__(self) -> None:
        if self._owns_http:
            self._http.close()

    def options_dict(self) -> dict[str, object]:
        return {
            "base_url": self._job.base_url,
            "report_ids": self._job.report_ids,
            "prefer_json_endpoint": self._job.prefer_json_endpoint,
            "include_page_content": self._job.include_page_content,
            "max_records": self._job.max_records,
            "discover_reports_via_graphql": self._job.discover_reports_via_graphql,
            "graphql_url": self._job.graphql_url,
            "discovery_page_size": self._job.discovery_page_size,
            "discovery_max_pages": self._job.discovery_max_pages,
        }

    def fetch_records(self) -> list[CybersecurityRecord]:
        return list(self.iter_records())

    def iter_records(self) -> Iterator[CybersecurityRecord]:
        report_ids, discovery_error = self._build_report_ids()

        yielded_count = 0
        failures: list[str] = []
        if discovery_error:
            failures.append(f"discovery: {discovery_error}")

        for report_id in report_ids:
            try:
                record = self._fetch_one(report_id)
            except Exception as exc:
                failures.append(f"{report_id}: {exc}")
                continue
            yield record
            yielded_count += 1
            if self._job.max_records is not None and yielded_count >= self._job.max_records:
                break

        if yielded_count == 0 and failures:
            failures_preview = "; ".join(failures[:3])
            raise ConnectorError(f"No HackerOne reports collected: {failures_preview}")
        if yielded_count == 0:
            raise ConnectorError(
                "No HackerOne reports collected: no candidate report IDs available."
            )

    def _build_report_ids(self) -> tuple[list[int], str | None]:
        report_ids = list(self._job.report_ids)
        discovery_error: str | None = None

        if self._job.discover_reports_via_graphql:
            try:
                max_needed: int | None = None
                if self._job.max_records is not None:
                    remaining = self._job.max_records - len(report_ids)
                    max_needed = max(remaining, 0)
                if max_needed != 0:
                    report_ids.extend(self._discover_report_ids(max_needed=max_needed))
            except Exception as exc:
                discovery_error = str(exc)

        return _unique_ints(report_ids), discovery_error

    def _discover_report_ids(self, *, max_needed: int | None = None) -> list[int]:
        discovered_ids: list[int] = []
        after_cursor: str | None = None
        pages_fetched = 0

        while True:
            payload = self._http.post_json(
                self._job.graphql_url,
                json={
                    "query": _REPORT_DISCOVERY_QUERY,
                    "variables": {
                        "first": self._job.discovery_page_size,
                        "after": after_cursor,
                    },
                },
            )

            if not isinstance(payload, dict):
                raise ConnectorError("HackerOne discovery response is not a JSON object.")

            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    message = _to_str_or_none(first_error.get("message"))
                else:
                    message = str(first_error)
                raise ConnectorError(
                    f"HackerOne discovery query failed: {message or 'unknown error'}"
                )

            data = payload.get("data")
            if not isinstance(data, dict):
                raise ConnectorError("HackerOne discovery response missing data object.")

            reports = data.get("reports")
            if not isinstance(reports, dict):
                raise ConnectorError("HackerOne discovery response missing reports connection.")

            nodes = reports.get("nodes")
            if not isinstance(nodes, list):
                raise ConnectorError("HackerOne discovery response missing nodes list.")

            for node in nodes:
                if not isinstance(node, dict):
                    continue
                report_id = _to_int_or_none(node.get("_id"))
                if report_id is None:
                    continue
                discovered_ids.append(report_id)
                if max_needed is not None and len(discovered_ids) >= max_needed:
                    return _unique_ints(discovered_ids)

            pages_fetched += 1
            if (
                self._job.discovery_max_pages is not None
                and pages_fetched >= self._job.discovery_max_pages
            ):
                break

            page_info = reports.get("pageInfo")
            if not isinstance(page_info, dict):
                raise ConnectorError("HackerOne discovery response missing pageInfo object.")

            has_next_page = bool(page_info.get("hasNextPage"))
            after_cursor = _to_str_or_none(page_info.get("endCursor"))
            if not has_next_page or after_cursor is None:
                break

        return _unique_ints(discovered_ids)

    def _fetch_one(self, report_id: int) -> CybersecurityRecord:
        report_url = f"{self._job.base_url.rstrip('/')}/{report_id}"
        report_json_url = f"{report_url}.json"

        title: str | None = None
        page_text = ""
        raw_text = ""
        published_at = None
        json_payload: dict[str, object] | None = None

        if self._job.prefer_json_endpoint:
            try:
                json_response = self._http.get_json(report_json_url)
                if isinstance(json_response, dict):
                    json_payload = json_response
                    title = _to_str_or_none(json_payload.get("title"))
                    if self._job.include_page_content:
                        page_text = (
                            _to_str_or_none(json_payload.get("vulnerability_information")) or ""
                        )
                    published_at = parse_datetime_utc(
                        _to_str_or_none(json_payload.get("submitted_at"))
                        or _to_str_or_none(json_payload.get("created_at"))
                        or _to_str_or_none(json_payload.get("disclosed_at"))
                    )
            except Exception:
                json_payload = None

        if title is None or (self._job.include_page_content and not page_text):
            html = self._http.get_text(report_url)
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                output_format="txt",
            )
            html_text = extracted.strip() if extracted else ""
            raw_text = html_text

            if title is None:
                title = self._extract_title(html_text)
            if self._job.include_page_content and not page_text:
                page_text = html_text
            if published_at is None:
                published_match = _PUBLISHED_RE.search(html_text)
                published_at = parse_datetime_utc(
                    published_match.group(1) if published_match else None
                )

        if _looks_like_js_placeholder(page_text):
            page_text = ""

        if title is None:
            title = f"HackerOne Report {report_id}"

        description = title
        if self._job.include_page_content and page_text:
            description = page_text

        json_cve_ids: list[str] = []
        if json_payload is not None:
            raw_cve_ids = json_payload.get("cve_ids")
            if isinstance(raw_cve_ids, list):
                json_cve_ids = [
                    str(item).strip().upper() for item in raw_cve_ids if str(item).strip()
                ]

        aliases = unique_str([*json_cve_ids, *extract_cve_ids(title, description)])

        references = [Reference(url=report_url, kind="report", source="hackerone")]
        if json_payload is not None:
            references.append(
                Reference(url=report_json_url, kind="report-json", source="hackerone")
            )

        return CybersecurityRecord(
            record_uid=f"hackerone_reports:{report_id}",
            source=DataSource.HACKERONE_REPORTS,
            source_record_id=str(report_id),
            title=title,
            summary=title,
            description=description,
            aliases=aliases,
            cve_ids=[alias for alias in aliases if alias.startswith("CVE-")],
            ghsa_ids=[],
            cwe_ids=[],
            published_at_utc=published_at,
            modified_at_utc=None,
            withdrawn_at_utc=None,
            vuln_status="disclosed-report",
            weaknesses=[],
            affected_targets=[
                AffectedTarget(
                    ecosystem=None,
                    package=None,
                    vendor=None,
                    product="hackerone-program",
                    versions=[],
                    cpe=None,
                )
            ],
            severities=[
                SeverityMetric(
                    scheme="HACKERONE",
                    source="hackerone",
                    vector=None,
                    score=None,
                    severity=None,
                )
            ],
            epss_score=None,
            epss_percentile=None,
            references=references,
            exploit_artifacts=[
                ExploitArtifact(
                    kind="report-page",
                    url=report_url,
                    content=page_text if self._job.include_page_content else None,
                )
            ],
            procedure=extract_procedure_evidence(description),
            tags=unique_str(["hackerone", "disclosed-report"]),
            raw={
                "report_id": report_id,
                "url": report_url,
                "json_url": report_json_url,
                "json": json_payload,
                "text": raw_text or page_text,
            },
        )

    def _extract_title(self, text: str) -> str | None:
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            match = _REPORT_TITLE_RE.match(candidate)
            if match:
                return match.group(1).strip()
        return None


def _looks_like_js_placeholder(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    return "javascript is disabled" in lowered and "enable javascript" in lowered


def _to_str_or_none(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _to_int_or_none(value: object) -> int | None:
    text = _to_str_or_none(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _unique_ints(values: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
