"""Connector factory and registry."""

from __future__ import annotations

from skill_learner.models import DataSource

from .base import BaseConnector
from .config import (
    ConnectorJob,
    ExploitDBJob,
    GitHubAdvisoriesJob,
    HackerOneReportsJob,
    NucleiTemplatesJob,
    NVDJob,
    PentesterLandJob,
)
from .exploit_db import ExploitDBConnector
from .github_advisories import GitHubAdvisoriesConnector
from .hackerone_reports import HackerOneReportsConnector
from .http import HTTPClient
from .nuclei_templates import NucleiTemplatesConnector
from .nvd import NVDConnector
from .pentester_land import PentesterLandConnector


def create_connector(job: ConnectorJob, http_client: HTTPClient | None = None) -> BaseConnector:
    """Instantiate the connector for a discriminated job configuration."""
    if isinstance(job, NVDJob):
        return NVDConnector(job, http_client=http_client)
    if isinstance(job, GitHubAdvisoriesJob):
        return GitHubAdvisoriesConnector(job, http_client=http_client)
    if isinstance(job, NucleiTemplatesJob):
        return NucleiTemplatesConnector(job, http_client=http_client)
    if isinstance(job, ExploitDBJob):
        return ExploitDBConnector(job, http_client=http_client)
    if isinstance(job, PentesterLandJob):
        return PentesterLandConnector(job, http_client=http_client)
    if isinstance(job, HackerOneReportsJob):
        return HackerOneReportsConnector(job, http_client=http_client)
    raise TypeError(f"Unsupported connector job type: {type(job)!r}")


def supported_sources() -> list[DataSource]:
    """Return all sources currently implemented in code."""
    return [
        DataSource.NVD,
        DataSource.GITHUB_ADVISORIES,
        DataSource.NUCLEI_TEMPLATES,
        DataSource.EXPLOIT_DB,
        DataSource.PENTESTER_LAND,
        DataSource.HACKERONE_REPORTS,
    ]
