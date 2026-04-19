"""Connector for GitHub Advisory Database REST API."""

from __future__ import annotations

import os
import re
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
from .config import GitHubAdvisoriesJob
from .http import HTTPClient
from .procedure import extract_procedure_evidence
from .utils import extract_cwe_ids, parse_datetime_utc, unique_str

_LINK_PART_RE = re.compile(r"<([^>]+)>;\s*rel=\"([^\"]+)\"")


class GitHubAdvisoriesConnector(BaseConnector):
    """Fetch and normalize records from GitHub Advisory Database API."""

    source = DataSource.GITHUB_ADVISORIES
    BASE_URL = "https://api.github.com/advisories"

    def __init__(self, job: GitHubAdvisoriesJob, http_client: HTTPClient | None = None) -> None:
        self._job = job
        self._http = http_client or HTTPClient()
        self._owns_http = http_client is None

    def __del__(self) -> None:
        if self._owns_http:
            self._http.close()

    def options_dict(self) -> dict[str, object]:
        return {
            "per_page": self._job.per_page,
            "max_records": self._job.max_records,
            "advisory_type": self._job.advisory_type,
            "ecosystem": self._job.ecosystem,
            "severity": self._job.severity,
            "include_withdrawn": self._job.include_withdrawn,
            "github_token_env": self._job.github_token_env,
        }

    def fetch_records(self) -> list[CybersecurityRecord]:
        return list(self.iter_records())

    def iter_records(self) -> Iterator[CybersecurityRecord]:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._job.github_token_env is not None:
            token = os.getenv(self._job.github_token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        params: dict[str, object] = {
            "per_page": self._job.per_page,
        }
        if self._job.advisory_type != "all":
            params["type"] = self._job.advisory_type
        if self._job.ecosystem:
            params["ecosystem"] = self._job.ecosystem
        if self._job.severity:
            params["severity"] = self._job.severity
        if not self._job.include_withdrawn:
            params["is_withdrawn"] = "false"

        next_url: str | None = self.BASE_URL
        next_params: dict[str, object] | None = params
        yielded_count = 0

        while next_url is not None:
            response = self._http.get(next_url, params=next_params, headers=headers)
            payload = response.json()
            if not isinstance(payload, list):
                raise ConnectorError("GitHub advisories response is not a list.")

            for item in payload:
                if not isinstance(item, dict):
                    continue
                yield self._to_record(item)
                yielded_count += 1
                if self._job.max_records is not None and yielded_count >= self._job.max_records:
                    return

            next_url = _next_link(response.headers.get("link"))
            next_params = None

    def _to_record(self, advisory: dict[str, Any]) -> CybersecurityRecord:
        ghsa_id = _to_str(advisory.get("ghsa_id")).strip()
        if not ghsa_id:
            raise ConnectorError("GitHub advisory record missing ghsa_id.")

        summary = _to_str_or_none(advisory.get("summary"))
        description = _to_str_or_none(advisory.get("description"))
        title = summary or ghsa_id

        aliases = self._parse_aliases(advisory)
        cve_ids = [identifier for identifier in aliases if identifier.startswith("CVE-")]
        ghsa_ids = [identifier for identifier in aliases if identifier.startswith("GHSA-")]

        cwe_ids: list[str] = []
        cwes = advisory.get("cwes")
        if isinstance(cwes, list):
            cwe_ids = [
                _to_str(item.get("cwe_id")).strip().upper()
                for item in cwes
                if isinstance(item, dict) and _to_str(item.get("cwe_id")).strip()
            ]
        cwe_ids = unique_str(cwe_ids + extract_cwe_ids(description or ""))

        references = self._parse_references(advisory)
        affected_targets = self._parse_affected(advisory)
        severities = self._parse_severities(advisory)

        full_text = "\n\n".join(part for part in [summary, description] if part)

        return CybersecurityRecord(
            record_uid=f"github_advisories:{ghsa_id}",
            source=DataSource.GITHUB_ADVISORIES,
            source_record_id=ghsa_id,
            title=title,
            summary=summary,
            description=description,
            aliases=aliases,
            cve_ids=cve_ids,
            ghsa_ids=ghsa_ids or [ghsa_id],
            cwe_ids=cwe_ids,
            published_at_utc=parse_datetime_utc(_to_str_or_none(advisory.get("published_at"))),
            modified_at_utc=parse_datetime_utc(_to_str_or_none(advisory.get("updated_at"))),
            withdrawn_at_utc=parse_datetime_utc(_to_str_or_none(advisory.get("withdrawn_at"))),
            vuln_status=_to_str_or_none(advisory.get("type")),
            weaknesses=cwe_ids,
            affected_targets=affected_targets,
            severities=severities,
            epss_score=_extract_epss_score(advisory),
            epss_percentile=_extract_epss_percentile(advisory),
            references=references,
            exploit_artifacts=[],
            procedure=extract_procedure_evidence(full_text),
            tags=unique_str(["github-advisory", _to_str(advisory.get("severity")).lower()]),
            raw=advisory,
        )

    def _parse_aliases(self, advisory: dict[str, Any]) -> list[str]:
        aliases: list[str] = []
        identifiers = advisory.get("identifiers")
        if isinstance(identifiers, list):
            for identifier in identifiers:
                if isinstance(identifier, dict):
                    value = _to_str(identifier.get("value")).strip().upper()
                    if value:
                        aliases.append(value)
        for field in ("ghsa_id", "cve_id"):
            value = _to_str(advisory.get(field)).strip().upper()
            if value:
                aliases.append(value)
        return unique_str(aliases)

    def _parse_references(self, advisory: dict[str, Any]) -> list[Reference]:
        refs: list[Reference] = []
        reference_urls = advisory.get("references")
        if isinstance(reference_urls, list):
            for url in reference_urls:
                if isinstance(url, str) and url.strip():
                    refs.append(Reference(url=url.strip(), kind="reference", source="github"))

        for key in ("html_url", "repository_advisory_url", "source_code_location", "url"):
            value = _to_str(advisory.get(key)).strip()
            if value:
                refs.append(Reference(url=value, kind=key, source="github"))
        return refs

    def _parse_affected(self, advisory: dict[str, Any]) -> list[AffectedTarget]:
        affected: list[AffectedTarget] = []
        vulnerabilities = advisory.get("vulnerabilities")
        if not isinstance(vulnerabilities, list):
            return affected

        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            package = vulnerability.get("package")
            package_name: str | None = None
            ecosystem: str | None = None
            if isinstance(package, dict):
                package_name = _to_str_or_none(package.get("name"))
                ecosystem = _to_str_or_none(package.get("ecosystem"))

            versions: list[str] = []
            vulnerable_range = _to_str_or_none(vulnerability.get("vulnerable_version_range"))
            if vulnerable_range:
                versions.append(vulnerable_range)
            first_patched = vulnerability.get("first_patched_version")
            if isinstance(first_patched, dict):
                patched_identifier = _to_str_or_none(first_patched.get("identifier"))
                if patched_identifier:
                    versions.append(f"patched:{patched_identifier}")

            affected.append(
                AffectedTarget(
                    ecosystem=ecosystem,
                    package=package_name,
                    vendor=None,
                    product=package_name,
                    versions=versions,
                    cpe=None,
                )
            )
        return affected

    def _parse_severities(self, advisory: dict[str, Any]) -> list[SeverityMetric]:
        out: list[SeverityMetric] = []

        qualitative = _to_str_or_none(advisory.get("severity"))
        if qualitative:
            out.append(
                SeverityMetric(
                    scheme="GHSA",
                    source="github",
                    vector=None,
                    score=None,
                    severity=qualitative,
                )
            )

        cvss_severities = advisory.get("cvss_severities")
        if isinstance(cvss_severities, dict):
            for key, entry in cvss_severities.items():
                if not isinstance(entry, dict):
                    continue
                out.append(
                    SeverityMetric(
                        scheme=key.upper(),
                        source="github",
                        vector=_to_str_or_none(entry.get("vector_string")),
                        score=_to_float_or_none(entry.get("score")),
                        severity=qualitative,
                    )
                )

        cvss = advisory.get("cvss")
        if isinstance(cvss, dict):
            score = _to_float_or_none(cvss.get("score"))
            vector = _to_str_or_none(cvss.get("vector_string"))
            if score is not None or vector is not None:
                out.append(
                    SeverityMetric(
                        scheme="CVSS",
                        source="github",
                        vector=vector,
                        score=score,
                        severity=qualitative,
                    )
                )
        return out


def _next_link(link_header: str | None) -> str | None:
    """Parse RFC5988 Link header and return URL for rel=next if present."""
    if not link_header:
        return None
    for match in _LINK_PART_RE.finditer(link_header):
        url, relation = match.group(1), match.group(2)
        if relation == "next":
            return url
    return None


def _extract_epss_score(advisory: dict[str, Any]) -> float | None:
    """Extract EPSS probability from advisory database_specific payload."""
    database_specific = advisory.get("database_specific")
    if isinstance(database_specific, dict):
        epss = database_specific.get("epss")
        if isinstance(epss, dict):
            return _to_float_or_none(epss.get("percentage"))
    return None


def _extract_epss_percentile(advisory: dict[str, Any]) -> float | None:
    """Extract EPSS percentile from advisory database_specific payload."""
    database_specific = advisory.get("database_specific")
    if isinstance(database_specific, dict):
        epss = database_specific.get("epss")
        if isinstance(epss, dict):
            return _to_float_or_none(epss.get("percentile"))
    return None


def _to_str(value: object) -> str:
    """Convert optional value to string, returning empty string for None."""
    return str(value) if value is not None else ""


def _to_str_or_none(value: object) -> str | None:
    """Return stripped string value or None when blank/missing."""
    text = _to_str(value).strip()
    return text or None


def _to_float_or_none(value: object) -> float | None:
    """Convert int/float values to float and reject non-numeric input."""
    if isinstance(value, int | float):
        return float(value)
    return None
