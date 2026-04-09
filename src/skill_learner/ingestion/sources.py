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


def _normalized_content_type(content_type_header: str | None) -> str | None:
    if content_type_header is None:
        return None
    return content_type_header.split(";", 1)[0].strip().lower()


def _looks_like_markdown_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".md") or lowered.endswith(".markdown")


def fetch_web_source(url: str, timeout_seconds: float = 15.0) -> tuple[str, dict[str, Any]]:
    """Fetch and extract web text using HTTPX + Trafilatura."""
    timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
    try:
        response = httpx.get(url, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceReadError(
            f"failed to fetch URL: {url} ({exc.__class__.__name__}: {exc})"
        ) from exc

    content_type = _normalized_content_type(response.headers.get("content-type"))
    response_url = str(response.url)
    response_text = response.text.strip()

    extraction_method = "trafilatura"
    extracted: str
    if (
        content_type in {"text/plain", "text/markdown"}
        or (content_type is not None and "markdown" in content_type)
        or _looks_like_markdown_url(response_url)
    ):
        extracted = response_text
        extraction_method = "raw_text"
    else:
        extracted_candidate = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,
            output_format="txt",
        )
        extracted = extracted_candidate.strip() if extracted_candidate is not None else ""

    if not extracted:
        raise SourceExtractionError(f"no extractable text found for URL: {url}")

    metadata: dict[str, Any] = {
        "final_url": response_url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "fetcher": "httpx",
        "extractor": "trafilatura",
        "extraction_method": extraction_method,
    }
    return extracted, metadata


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
