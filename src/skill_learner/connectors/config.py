"""Validated schema for connector jobs and benchmark execution packs.

The CLI loads YAML into these Pydantic models before dispatching work to the
runner. Field constraints here are the single source of truth for connector
configuration validation.
"""

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

    source: Literal["nvd"] = Field(
        description="Discriminator that routes this job to the NVD connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    api_key_env: str | None = Field(
        default="NVD_API_KEY",
        description="Environment variable name containing the NVD API key.",
    )
    results_per_page: int = Field(
        default=2000,
        ge=1,
        le=2000,
        description="NVD page size per API call (NVD currently allows at most 2000).",
    )
    modified_start: datetime | None = Field(
        default=None,
        description="Lower bound for last-modified filtering (timezone-aware datetime).",
    )
    modified_end: datetime | None = Field(
        default=None,
        description="Upper bound for last-modified filtering (timezone-aware datetime).",
    )


class GitHubAdvisoriesJob(BaseModel):
    """Configuration for GitHub Advisory Database API connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["github_advisories"] = Field(
        description="Discriminator that routes this job to the GitHub advisories connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    github_token_env: str | None = Field(
        default="GITHUB_TOKEN",
        description="Environment variable name containing a GitHub API token.",
    )
    per_page: int = Field(
        default=100,
        ge=1,
        le=100,
        description="GitHub API page size (maximum allowed by endpoint is 100).",
    )
    advisory_type: Literal["reviewed", "unreviewed", "malware", "all"] = Field(
        default="reviewed",
        description="Server-side advisory filter applied by the GitHub API.",
    )
    ecosystem: str | None = Field(
        default=None,
        description="Optional ecosystem filter such as pip, npm, or maven.",
    )
    severity: Literal["low", "medium", "high", "critical"] | None = Field(
        default=None,
        description="Optional minimum severity label filter enforced by the API.",
    )
    include_withdrawn: bool = Field(
        default=False,
        description="Include withdrawn advisories when true.",
    )


class NucleiTemplatesJob(BaseModel):
    """Configuration for Nuclei template corpus connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["nuclei_templates"] = Field(
        description="Discriminator that routes this job to the nuclei templates connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    cves_url: str = Field(
        default=(
            "https://raw.githubusercontent.com/projectdiscovery/nuclei-templates/main/cves.json"
        ),
        description="Line-delimited JSON index URL used as nuclei record entry point.",
    )
    raw_root_url: str = Field(
        default=("https://raw.githubusercontent.com/projectdiscovery/nuclei-templates/main"),
        description="Base URL used to build absolute template file links.",
    )
    include_template_content: bool = Field(
        default=True,
        description="Fetch and embed template YAML content in artifacts when true.",
    )


class ExploitDBJob(BaseModel):
    """Configuration for Exploit-DB connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["exploit_db"] = Field(
        description="Discriminator that routes this job to the Exploit-DB connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    csv_url: str = Field(
        default=("https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"),
        description="CSV index URL that enumerates exploit metadata rows.",
    )
    raw_root_url: str = Field(
        default="https://gitlab.com/exploit-database/exploitdb/-/raw/main",
        description="Base URL used to construct raw exploit source file links.",
    )
    include_exploit_source: bool = Field(
        default=True,
        description="Attempt to fetch raw exploit source text for each entry.",
    )
    include_only_verified: bool = Field(
        default=False,
        description="Keep only rows marked as verified by Exploit-DB.",
    )
    type_filter: list[str] = Field(
        default_factory=list,
        description="Optional allow-list of exploit types; empty means all types.",
    )
    platform_filter: list[str] = Field(
        default_factory=list,
        description="Optional allow-list of platform values; empty means all platforms.",
    )


class PentesterLandJob(BaseModel):
    """Configuration for Pentester.land writeups connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["pentester_land"] = Field(
        description="Discriminator that routes this job to the pentester.land connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    json_url: str = Field(
        default="https://pentester.land/writeups.json",
        description="JSON feed URL containing indexed writeup metadata.",
    )
    include_link_content: bool = Field(
        default=True,
        description="Fetch linked writeup pages and extract plain text when true.",
    )
    max_links_per_record: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Maximum number of links fetched per writeup entry.",
    )


class HackerOneReportsJob(BaseModel):
    """Configuration for disclosed HackerOne report connector."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["hackerone_reports"] = Field(
        description="Discriminator that routes this job to the HackerOne reports connector.",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this job should run; disabled jobs are reported as skipped.",
    )
    max_records: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on emitted records for this job.",
    )
    base_url: str = Field(
        default="https://hackerone.com/reports",
        description="Base public URL used to construct report page endpoints.",
    )
    report_ids: list[int] = Field(
        default_factory=list,
        description="Explicit disclosed report IDs to collect.",
    )
    prefer_json_endpoint: bool = Field(
        default=True,
        description="Try '<report>.json' before scraping HTML content.",
    )
    include_page_content: bool = Field(
        default=True,
        description="Include extracted report body text when available.",
    )
    discover_reports_via_graphql: bool = Field(
        default=False,
        description="Enable public report ID discovery via GraphQL pagination.",
    )
    graphql_url: str = Field(
        default="https://hackerone.com/graphql",
        description="GraphQL endpoint used for optional report discovery.",
    )
    discovery_page_size: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Number of report IDs requested per GraphQL discovery page.",
    )
    discovery_max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Optional safety bound on GraphQL discovery pagination depth.",
    )

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

    benchmark_id: str = Field(
        min_length=1,
        description="Run identifier used in output directory layout and metadata.",
    )
    task: str | None = Field(
        default=None,
        description="Optional human-readable task label for experiment bookkeeping.",
    )
    generated_on: str | None = Field(
        default=None,
        description="Optional timestamp string captured when the pack was generated.",
    )
    max_concurrent_jobs: int = Field(
        default=1,
        ge=1,
        le=32,
        description="Default worker count for pack execution when CLI override is absent.",
    )
    jobs: list[ConnectorJob] = Field(
        min_length=1,
        description="Ordered connector job definitions executed by the runner.",
    )


def load_connector_pack(path: Path) -> ConnectorPack:
    """Read and validate a connector pack YAML file."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Connector pack must be a YAML mapping.")
    return ConnectorPack.model_validate(payload)


def source_name(job: ConnectorJob) -> DataSource:
    """Return enum source name from a discriminated job value."""
    return DataSource(job.source)
