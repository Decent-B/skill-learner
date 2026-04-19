"""Connector for National Vulnerability Database CVE API v2."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from skill_learner.models import (
    AffectedTarget,
    CybersecurityRecord,
    DataSource,
    Reference,
    SeverityMetric,
)

from .base import BaseConnector, ConnectorError
from .config import NVDJob
from .http import HTTPClient
from .procedure import extract_procedure_evidence
from .utils import extract_cwe_ids, parse_datetime_utc, unique_str


class NVDConnector(BaseConnector):
    """Fetch and normalize NVD CVE records."""

    source = DataSource.NVD
    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, job: NVDJob, http_client: HTTPClient | None = None) -> None:
        self._job = job
        self._http = http_client or HTTPClient()
        self._owns_http = http_client is None

    def __del__(self) -> None:
        if self._owns_http:
            self._http.close()

    def options_dict(self) -> dict[str, object]:
        return {
            "results_per_page": self._job.results_per_page,
            "max_records": self._job.max_records,
            "modified_start": self._job.modified_start.isoformat()
            if self._job.modified_start is not None
            else None,
            "modified_end": self._job.modified_end.isoformat()
            if self._job.modified_end is not None
            else None,
            "api_key_env": self._job.api_key_env,
        }

    def fetch_records(self) -> list[CybersecurityRecord]:
        return list(self.iter_records())

    def iter_records(self) -> Iterator[CybersecurityRecord]:
        headers: dict[str, str] = {}
        if self._job.api_key_env is not None:
            api_key = os.getenv(self._job.api_key_env)
            if api_key:
                headers["apiKey"] = api_key

        yielded_count = 0
        start_index = 0
        total_results: int | None = None

        while True:
            params: dict[str, object] = {
                "startIndex": start_index,
                "resultsPerPage": self._job.results_per_page,
            }
            if self._job.modified_start is not None:
                params["lastModStartDate"] = self._job.modified_start.astimezone().isoformat()
            if self._job.modified_end is not None:
                params["lastModEndDate"] = self._job.modified_end.astimezone().isoformat()

            payload = self._http.get_json(self.BASE_URL, params=params, headers=headers or None)
            if not isinstance(payload, dict):
                raise ConnectorError("NVD response is not a JSON object.")

            vulnerabilities = payload.get("vulnerabilities")
            if not isinstance(vulnerabilities, list):
                raise ConnectorError("NVD response does not include a vulnerabilities list.")

            if total_results is None:
                total_raw = payload.get("totalResults")
                if isinstance(total_raw, int):
                    total_results = total_raw

            if not vulnerabilities:
                break

            for entry in vulnerabilities:
                cve_obj = entry.get("cve") if isinstance(entry, dict) else None
                if not isinstance(cve_obj, dict):
                    continue
                yield self._to_record(cve_obj)
                yielded_count += 1
                if self._job.max_records is not None and yielded_count >= self._job.max_records:
                    return

            page_size = payload.get("resultsPerPage")
            if not isinstance(page_size, int) or page_size <= 0:
                page_size = len(vulnerabilities)
            start_index += page_size

            if total_results is not None and start_index >= total_results:
                break

    def _to_record(self, cve: dict[str, Any]) -> CybersecurityRecord:
        cve_id = str(cve.get("id", "")).strip()
        if not cve_id:
            raise ConnectorError("NVD CVE record is missing id.")

        description = self._pick_english_description(cve.get("descriptions"))
        title = self._derive_title(cve_id=cve_id, description=description)

        references = self._parse_references(cve.get("references"))
        weaknesses = self._parse_weaknesses(cve.get("weaknesses"))
        cwe_ids = extract_cwe_ids(" ".join(weaknesses))

        return CybersecurityRecord(
            record_uid=f"nvd:{cve_id}",
            source=DataSource.NVD,
            source_record_id=cve_id,
            title=title,
            summary=description,
            description=description,
            aliases=[cve_id],
            cve_ids=[cve_id],
            ghsa_ids=[],
            cwe_ids=cwe_ids,
            published_at_utc=parse_datetime_utc(_to_str(cve.get("published"))),
            modified_at_utc=parse_datetime_utc(_to_str(cve.get("lastModified"))),
            withdrawn_at_utc=None,
            vuln_status=_to_str_or_none(cve.get("vulnStatus")),
            weaknesses=weaknesses,
            affected_targets=self._parse_affected_targets(cve.get("configurations")),
            severities=self._parse_severities(cve.get("metrics")),
            epss_score=None,
            epss_percentile=None,
            references=references,
            exploit_artifacts=[],
            procedure=extract_procedure_evidence(description),
            tags=unique_str(["nvd", "cve"] + cwe_ids),
            raw=cve,
        )

    def _derive_title(self, *, cve_id: str, description: str) -> str:
        """Build a stable title even when upstream descriptions are malformed."""
        if description:
            first_sentence = description.split(".", maxsplit=1)[0].strip()
            if len(first_sentence) >= 2:
                return first_sentence
        if len(cve_id) >= 2:
            return cve_id
        return f"NVD record {cve_id}".strip()

    def _pick_english_description(self, descriptions: object) -> str:
        if not isinstance(descriptions, list):
            return ""
        english_values = [
            _to_str(item.get("value"))
            for item in descriptions
            if isinstance(item, dict) and _to_str(item.get("lang")).lower() == "en"
        ]
        if english_values:
            return english_values[0].strip()
        fallback_values = [
            _to_str(item.get("value")) for item in descriptions if isinstance(item, dict)
        ]
        return fallback_values[0].strip() if fallback_values else ""

    def _parse_references(self, references: object) -> list[Reference]:
        if not isinstance(references, list):
            return []
        out: list[Reference] = []
        for item in references:
            if not isinstance(item, dict):
                continue
            url = _to_str(item.get("url")).strip()
            if not url:
                continue
            out.append(
                Reference(
                    url=url,
                    kind="reference",
                    source=_to_str_or_none(item.get("source")),
                )
            )
        return out

    def _parse_weaknesses(self, weaknesses: object) -> list[str]:
        if not isinstance(weaknesses, list):
            return []
        values: list[str] = []
        for weakness in weaknesses:
            if not isinstance(weakness, dict):
                continue
            descriptions = weakness.get("description")
            if not isinstance(descriptions, list):
                continue
            for desc in descriptions:
                if isinstance(desc, dict):
                    value = _to_str(desc.get("value")).strip()
                    if value:
                        values.append(value)
        return unique_str(values)

    def _parse_affected_targets(self, configurations: object) -> list[AffectedTarget]:
        if not isinstance(configurations, list):
            return []

        targets: list[AffectedTarget] = []
        for config in configurations:
            if not isinstance(config, dict):
                continue
            nodes = config.get("nodes")
            if not isinstance(nodes, list):
                continue
            for match in _collect_cpe_matches(nodes):
                cpe = _to_str(match.get("criteria")).strip()
                if not cpe:
                    continue
                vendor, product, version = _parse_cpe23(cpe)
                targets.append(
                    AffectedTarget(
                        ecosystem=None,
                        package=None,
                        vendor=vendor,
                        product=product,
                        versions=[version] if version else [],
                        cpe=cpe,
                    )
                )
        return targets

    def _parse_severities(self, metrics: object) -> list[SeverityMetric]:
        if not isinstance(metrics, dict):
            return []

        out: list[SeverityMetric] = []
        for key, value in metrics.items():
            if not key.startswith("cvssMetric") or not isinstance(value, list):
                continue
            for metric in value:
                if not isinstance(metric, dict):
                    continue
                cvss_data = metric.get("cvssData")
                if not isinstance(cvss_data, dict):
                    continue
                version = _to_str(cvss_data.get("version"))
                out.append(
                    SeverityMetric(
                        scheme=f"CVSS:{version}" if version else key,
                        source=_to_str_or_none(metric.get("source")),
                        vector=_to_str_or_none(cvss_data.get("vectorString")),
                        score=_to_float_or_none(cvss_data.get("baseScore")),
                        severity=_to_str_or_none(metric.get("baseSeverity")),
                    )
                )
        return out


def _to_str(value: object) -> str:
    return str(value) if value is not None else ""


def _to_str_or_none(value: object) -> str | None:
    text = _to_str(value).strip()
    return text or None


def _to_float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _collect_cpe_matches(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        cpe_matches = node.get("cpeMatch")
        if isinstance(cpe_matches, list):
            out.extend(item for item in cpe_matches if isinstance(item, dict))
        children = node.get("children")
        if isinstance(children, list):
            child_nodes = [item for item in children if isinstance(item, dict)]
            out.extend(_collect_cpe_matches(child_nodes))
    return out


def _parse_cpe23(cpe: str) -> tuple[str | None, str | None, str | None]:
    parts = cpe.split(":")
    if len(parts) < 6:
        return None, None, None
    vendor = parts[3] if parts[3] not in {"*", "-"} else None
    product = parts[4] if parts[4] not in {"*", "-"} else None
    version = parts[5] if parts[5] not in {"*", "-"} else None
    return vendor, product, version
