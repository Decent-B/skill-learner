"""Typed connector execution configuration and pack loading."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from skill_learner.models import DataSource


class NVDJob(BaseModel):
    """Configuration for the NVD CVE API connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["nvd"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    api_key_env: str | None = "NVD_API_KEY"
    results_per_page: int = Field(default=2000, ge=1, le=2000)
    modified_start: datetime | None = None
    modified_end: datetime | None = None


class GitHubAdvisoriesJob(BaseModel):
    """Configuration for GitHub Advisory Database API connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["github_advisories"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    github_token_env: str | None = "GITHUB_TOKEN"
    per_page: int = Field(default=100, ge=1, le=100)
    advisory_type: Literal["reviewed", "unreviewed", "malware", "all"] = "reviewed"
    ecosystem: str | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    include_withdrawn: bool = False


class NucleiTemplatesJob(BaseModel):
    """Configuration for Nuclei template corpus connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["nuclei_templates"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    cves_url: str = "https://raw.githubusercontent.com/projectdiscovery/nuclei-templates/main/cves.json"
    raw_root_url: str = "https://raw.githubusercontent.com/projectdiscovery/nuclei-templates/main"
    include_template_content: bool = True


class ExploitDBJob(BaseModel):
    """Configuration for Exploit-DB connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["exploit_db"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    csv_url: str = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"
    raw_root_url: str = "https://gitlab.com/exploit-database/exploitdb/-/raw/main"
    include_exploit_source: bool = True
    include_only_verified: bool = False
    type_filter: list[str] = Field(default_factory=list)
    platform_filter: list[str] = Field(default_factory=list)


class PentesterLandJob(BaseModel):
    """Configuration for Pentester.land writeups connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["pentester_land"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    json_url: str = "https://pentester.land/writeups.json"
    include_link_content: bool = True
    max_links_per_record: int = Field(default=2, ge=0, le=20)


class HackerOneReportsJob(BaseModel):
    """Configuration for disclosed HackerOne report connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["hackerone_reports"]
    enabled: bool = True
    max_records: int | None = Field(default=None, ge=1)
    base_url: str = "https://hackerone.com/reports"
    report_ids: list[int] = Field(default_factory=list)
    prefer_json_endpoint: bool = True
    include_page_content: bool = True
    discover_reports_via_graphql: bool = False
    graphql_url: str = "https://hackerone.com/graphql"
    discovery_page_size: int = Field(default=100, ge=1, le=100)
    discovery_max_pages: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_report_sources(self) -> HackerOneReportsJob:
        """Require at least one static ID or discovery strategy."""
        if not self.report_ids and not self.discover_reports_via_graphql:
            raise ValueError(
                "hackerone_reports requires report_ids or discover_reports_via_graphql=true"
            )
        return self


ConnectorJob = Annotated[
    NVDJob
    | GitHubAdvisoriesJob
    | NucleiTemplatesJob
    | ExploitDBJob
    | PentesterLandJob
    | HackerOneReportsJob,
    Field(discriminator="source"),
]


class ConnectorPack(BaseModel):
    """Top-level pack for orchestrating connector jobs."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str = Field(min_length=1)
    task: str | None = None
    generated_on: str | None = None
    max_concurrent_jobs: int = Field(default=1, ge=1, le=32)
    jobs: list[ConnectorJob] = Field(min_length=1)


def load_connector_pack(path: Path) -> ConnectorPack:
    """Read and validate a connector pack YAML file."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Connector pack must be a YAML mapping.")
    return ConnectorPack.model_validate(payload)


def source_name(job: ConnectorJob) -> DataSource:
    """Return enum source name from a discriminated job value."""
    return DataSource(job.source)
