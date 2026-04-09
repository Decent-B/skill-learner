"""Unit tests for source adapter helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skill_learner.ingestion.sources import (
    SourceExtractionError,
    fetch_web_source,
    read_pdf_source,
    read_text_source,
)


def test_read_text_source_reads_content(tmp_path: Path) -> None:
    path = tmp_path / "doc.txt"
    path.write_text("hello world", encoding="utf-8")
    text, metadata = read_text_source(path)
    assert text == "hello world"
    assert metadata["encoding"] == "utf-8"


def test_read_text_source_raises_on_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(SourceExtractionError):
        read_text_source(path)


def test_fetch_web_source_uses_extractors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.text = "<html><body>workflow steps</body></html>"
            self.status_code = 200
            self.url = "https://example.com/doc"
            self.headers = {"content-type": "text/html"}

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, follow_redirects: bool, timeout: Any) -> FakeResponse:
        assert url == "https://example.com/doc"
        assert follow_redirects is True
        assert timeout is not None
        return FakeResponse()

    def fake_extract(
        text: str,
        include_comments: bool,
        include_tables: bool,
        output_format: str,
    ) -> str:
        assert "workflow steps" in text
        assert include_comments is False
        assert include_tables is True
        assert output_format == "txt"
        return "step 1\nstep 2"

    monkeypatch.setattr("skill_learner.ingestion.sources.httpx.get", fake_get)
    monkeypatch.setattr("skill_learner.ingestion.sources.trafilatura.extract", fake_extract)

    text, metadata = fetch_web_source("https://example.com/doc")
    assert "step 1" in text
    assert metadata["status_code"] == 200
    assert metadata["extraction_method"] == "trafilatura"


def test_fetch_web_source_keeps_raw_markdown_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.text = "# Setup Java\n\nRun `mvn -B verify`\n"
            self.status_code = 200
            self.url = "https://raw.githubusercontent.com/actions/setup-java/main/README.md"
            self.headers = {"content-type": "text/plain; charset=utf-8"}

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, follow_redirects: bool, timeout: Any) -> FakeResponse:
        assert url.endswith("/README.md")
        assert follow_redirects is True
        assert timeout is not None
        return FakeResponse()

    def fake_extract(*_: Any, **__: Any) -> str:
        raise AssertionError("trafilatura.extract should not run for markdown/plaintext responses")

    monkeypatch.setattr("skill_learner.ingestion.sources.httpx.get", fake_get)
    monkeypatch.setattr("skill_learner.ingestion.sources.trafilatura.extract", fake_extract)

    text, metadata = fetch_web_source(
        "https://raw.githubusercontent.com/actions/setup-java/main/README.md"
    )
    assert "Setup Java" in text
    assert metadata["extraction_method"] == "raw_text"


def test_read_pdf_source_with_mocked_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, _: str) -> None:
            self.pages = [FakePage("page one"), FakePage("page two")]

    monkeypatch.setattr("skill_learner.ingestion.sources.PdfReader", FakeReader)
    text, metadata = read_pdf_source(pdf_path)
    assert "page one" in text
    assert metadata["page_count"] == 2
