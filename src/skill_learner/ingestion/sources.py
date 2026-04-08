"""Source adapters that extract text from different source types."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import trafilatura
from pypdf import PdfReader


class IngestionError(RuntimeError):
    """Base ingestion failure."""


class SourceReadError(IngestionError):
    """Raised when source bytes cannot be loaded."""


class SourceExtractionError(IngestionError):
    """Raised when text extraction yields no useful text."""


def fetch_web_source(url: str, timeout_seconds: float = 15.0) -> tuple[str, dict[str, Any]]:
    """Fetch and extract web text using HTTPX + Trafilatura."""
    timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
    try:
        response = httpx.get(url, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceReadError(f"failed to fetch URL: {url}") from exc

    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )
    if extracted is None or not extracted.strip():
        raise SourceExtractionError(f"no extractable text found for URL: {url}")

    metadata: dict[str, Any] = {
        "final_url": str(response.url),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "fetcher": "httpx",
        "extractor": "trafilatura",
    }
    return extracted.strip(), metadata


def read_pdf_source(path: Path) -> tuple[str, dict[str, Any]]:
    """Read PDF and concatenate extracted text in page order."""
    if not path.exists() or not path.is_file():
        raise SourceReadError(f"PDF file does not exist: {path}")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - third-party parser details
        raise SourceReadError(f"failed to read PDF: {path}") from exc

    page_text_chunks: list[str] = []
    for page in reader.pages:
        page_text_chunks.append((page.extract_text() or "").strip())

    text = "\n\n".join(page_text_chunks).strip()
    if not text:
        raise SourceExtractionError(f"no extractable text found in PDF: {path}")

    metadata: dict[str, Any] = {
        "source_path": str(path.resolve()),
        "page_count": len(reader.pages),
    }
    return text, metadata


def read_text_source(path: Path, encoding: str = "utf-8") -> tuple[str, dict[str, Any]]:
    """Read plain text files from local disk."""
    if not path.exists() or not path.is_file():
        raise SourceReadError(f"text file does not exist: {path}")

    try:
        text = path.read_text(encoding=encoding)
    except OSError as exc:
        raise SourceReadError(f"failed to read text file: {path}") from exc

    if not text.strip():
        raise SourceExtractionError(f"text file is empty: {path}")

    metadata: dict[str, Any] = {
        "source_path": str(path.resolve()),
        "encoding": encoding,
    }
    return text, metadata
