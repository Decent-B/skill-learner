"""Utility helpers shared by connector implementations."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime

_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", flags=re.IGNORECASE)
_GHSA_RE = re.compile(r"\bGHSA(?:-[23456789cfghjmpqrvwx]{4}){3}\b", flags=re.IGNORECASE)
_CWE_RE = re.compile(r"\bCWE-\d+\b", flags=re.IGNORECASE)


def unique_str(values: Iterable[str]) -> list[str]:
    """Return de-duplicated strings while preserving first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def parse_datetime_utc(value: str | None) -> datetime | None:
    """Parse known timestamp formats and normalize to UTC."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%Y-%m-%d",
            "%B %d, %Y, %I:%M%p UTC",
            "%b %d, %Y, %I:%M%p UTC",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def extract_cve_ids(*texts: str) -> list[str]:
    """Extract unique CVE identifiers from arbitrary text fields."""
    matches: list[str] = []
    for text in texts:
        matches.extend(match.group(0).upper() for match in _CVE_RE.finditer(text))
    return unique_str(matches)


def extract_ghsa_ids(*texts: str) -> list[str]:
    """Extract unique GHSA identifiers from arbitrary text fields."""
    matches: list[str] = []
    for text in texts:
        matches.extend(match.group(0).upper() for match in _GHSA_RE.finditer(text))
    return unique_str(matches)


def extract_cwe_ids(*texts: str) -> list[str]:
    """Extract unique CWE identifiers from arbitrary text fields."""
    matches: list[str] = []
    for text in texts:
        matches.extend(match.group(0).upper() for match in _CWE_RE.finditer(text))
    return unique_str(matches)
