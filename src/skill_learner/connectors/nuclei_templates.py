"""Connector for ProjectDiscovery nuclei-templates vulnerability corpus."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import yaml  # type: ignore[import-untyped]

from skill_learner.models import (
    AffectedTarget,
    CybersecurityRecord,
    DataSource,
    ExploitArtifact,
    Reference,
    SeverityMetric,
)

from .base import BaseConnector, ConnectorError
from .config import NucleiTemplatesJob
from .http import HTTPClient
from .procedure import extract_procedure_evidence
from .utils import extract_cve_ids, extract_cwe_ids, parse_datetime_utc, unique_str


class NucleiTemplatesConnector(BaseConnector):
    """Fetch and normalize records from Nuclei cves.json and template files."""

    source = DataSource.NUCLEI_TEMPLATES

    def __init__(self, job: NucleiTemplatesJob, http_client: HTTPClient | None = None) -> None:
        self._job = job
        self._http = http_client or HTTPClient()
        self._owns_http = http_client is None

    def __del__(self) -> None:
        if self._owns_http:
            self._http.close()

    def options_dict(self) -> dict[str, object]:
        return {
            "cves_url": self._job.cves_url,
            "raw_root_url": self._job.raw_root_url,
            "include_template_content": self._job.include_template_content,
            "max_records": self._job.max_records,
        }

    def fetch_records(self) -> list[CybersecurityRecord]:
        return list(self.iter_records())

    def iter_records(self) -> Iterator[CybersecurityRecord]:
        cves_text = self._http.get_text(self._job.cves_url)

        yielded_count = 0
        for line in cves_text.splitlines():
            entry_line = line.strip()
            if not entry_line:
                continue
            try:
                entry = json.loads(entry_line)
            except json.JSONDecodeError as exc:
                raise ConnectorError(f"Invalid nuclei cves.json entry: {exc}") from exc

            if not isinstance(entry, dict):
                continue
            yield self._to_record(entry)
            yielded_count += 1
            if self._job.max_records is not None and yielded_count >= self._job.max_records:
                return

    def _to_record(self, entry: dict[str, Any]) -> CybersecurityRecord:
        template_id = _to_str(entry.get("ID")).strip()
        if not template_id:
            raise ConnectorError("Nuclei record is missing ID.")

        info = entry.get("Info")
        if not isinstance(info, dict):
            info = {}

        title = _to_str_or_none(info.get("Name")) or template_id
        description = _to_str_or_none(info.get("Description"))
        severity = _to_str_or_none(info.get("Severity"))
        file_path = _to_str_or_none(entry.get("file_path"))

        template_url = (
            f"{self._job.raw_root_url.rstrip('/')}/{file_path.lstrip('/')}"
            if file_path is not None
            else None
        )

        template_text: str | None = None
        template_yaml: dict[str, Any] | None = None
        if self._job.include_template_content and template_url is not None:
            try:
                template_text = self._http.get_text(template_url)
            except Exception:
                template_text = None
            if template_text:
                parsed_yaml = yaml.safe_load(template_text)
                if isinstance(parsed_yaml, dict):
                    template_yaml = parsed_yaml

        classification = info.get("Classification")
        if not isinstance(classification, dict):
            classification = {}

        aliases = unique_str(
            [
                template_id,
                _to_str(classification.get("cve-id")).upper(),
                *extract_cve_ids(template_id, description or ""),
            ]
        )
        cve_ids = [alias for alias in aliases if alias.startswith("CVE-")]
        cwe_ids = unique_str(
            [
                _to_str(classification.get("cwe-id")).upper(),
                *extract_cwe_ids(description or ""),
            ]
        )

        references: list[Reference] = []
        ref_values = info.get("reference")
        if isinstance(ref_values, list):
            for ref in ref_values:
                if isinstance(ref, str) and ref.strip():
                    references.append(Reference(url=ref.strip(), kind="reference", source="nuclei"))
        if template_url is not None:
            references.append(Reference(url=template_url, kind="template", source="nuclei"))

        metadata = info.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        affected = [
            AffectedTarget(
                ecosystem=None,
                package=None,
                vendor=_to_str_or_none(metadata.get("vendor")),
                product=_to_str_or_none(metadata.get("product")),
                versions=[],
                cpe=_to_str_or_none(classification.get("cpe")),
            )
        ]

        severities = [
            SeverityMetric(
                scheme="NUCLEI",
                source="nuclei",
                vector=_to_str_or_none(classification.get("cvss-metrics")),
                score=_to_float_or_none(classification.get("cvss-score"))
                or _to_float_or_none(classification.get("CVSSScore")),
                severity=severity,
            )
        ]

        epss_score = _to_float_or_none(classification.get("epss-score"))
        epss_percentile = _to_float_or_none(classification.get("epss-percentile"))

        full_text_parts = [description or ""]
        if template_text:
            full_text_parts.append(template_text)
        procedure = extract_procedure_evidence("\n\n".join(full_text_parts))

        exploit_artifacts: list[ExploitArtifact] = []
        if template_url is not None:
            exploit_artifacts.append(
                ExploitArtifact(
                    kind="nuclei-template",
                    url=template_url,
                    content=template_text,
                )
            )

        tags = _parse_tags(info.get("tags"))

        raw_payload: dict[str, Any] = {
            "entry": entry,
            "template": template_yaml,
        }

        return CybersecurityRecord(
            record_uid=f"nuclei_templates:{template_id}",
            source=DataSource.NUCLEI_TEMPLATES,
            source_record_id=template_id,
            title=title,
            summary=description,
            description=description,
            aliases=aliases,
            cve_ids=cve_ids,
            ghsa_ids=[],
            cwe_ids=cwe_ids,
            published_at_utc=None,
            modified_at_utc=parse_datetime_utc(_to_str_or_none(metadata.get("last-modified"))),
            withdrawn_at_utc=None,
            vuln_status="template",
            weaknesses=cwe_ids,
            affected_targets=affected,
            severities=severities,
            epss_score=epss_score,
            epss_percentile=epss_percentile,
            references=references,
            exploit_artifacts=exploit_artifacts,
            procedure=procedure,
            tags=unique_str(["nuclei", "template", *tags]),
            raw=raw_payload,
        )


def _parse_tags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return unique_str([item.strip().lower() for item in value.split(",") if item.strip()])
    if isinstance(value, list):
        return unique_str([str(item).strip().lower() for item in value if str(item).strip()])
    return []


def _to_str(value: object) -> str:
    return str(value) if value is not None else ""


def _to_str_or_none(value: object) -> str | None:
    text = _to_str(value).strip()
    return text or None


def _to_float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
