"""Base contracts for cybersecurity source connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from skill_learner.models import CybersecurityRecord, DataSource


class ConnectorError(RuntimeError):
    """Raised when a connector cannot complete retrieval or parsing."""


class BaseConnector(ABC):
    """Abstract base class for all source connectors."""

    source: DataSource

    @abstractmethod
    def fetch_records(self) -> list[CybersecurityRecord]:
        """Fetch and normalize records from an upstream source."""

    def iter_records(self) -> Iterator[CybersecurityRecord]:
        """Iterate normalized records, defaulting to list-based fetch behavior."""
        yield from self.fetch_records()

    @abstractmethod
    def options_dict(self) -> dict[str, object]:
        """Return sanitized connector options captured in run metadata."""
