#!/usr/bin/env python3
"""Standalone dataset viewer server for normalized cybersecurity record outputs.

This server is intentionally isolated from the ingestion backend. It reads
existing JSONL and metadata artifacts from datasets/cybersecurity_records
(or a custom directory) and exposes a lightweight API plus static frontend.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASETS_ROOT = PROJECT_ROOT / "datasets" / "cybersecurity_records"
STATIC_ROOT = Path(__file__).resolve().parent / "static"

# key -> (mtime_ns, size_bytes, line_count)
_LINE_COUNT_CACHE: dict[str, tuple[int, int, int]] = {}


@dataclass(frozen=True)
class SourceArtifacts:
    """Latest JSONL and metadata files discovered under one source directory."""

    latest_jsonl: Path | None
    latest_meta: Path | None


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read JSON object from disk and return None for invalid/unreadable payloads."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _latest_artifacts(source_dir: Path) -> SourceArtifacts:
    """Return latest JSONL and metadata files for a source directory."""
    jsonl_files = sorted(source_dir.glob("*.jsonl"))
    meta_files = sorted(source_dir.glob("*.meta.json"))
    return SourceArtifacts(
        latest_jsonl=jsonl_files[-1] if jsonl_files else None,
        latest_meta=meta_files[-1] if meta_files else None,
    )


def _count_jsonl_records(path: Path) -> int:
    """Count non-empty JSONL lines with a small mtime/size cache."""
    cache_key = str(path.resolve())
    stat = path.stat()
    cached = _LINE_COUNT_CACHE.get(cache_key)
    if cached is not None:
        mtime_ns, size_bytes, line_count = cached
        if mtime_ns == stat.st_mtime_ns and size_bytes == stat.st_size:
            return line_count

    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            if raw_line.strip():
                count += 1

    _LINE_COUNT_CACHE[cache_key] = (stat.st_mtime_ns, stat.st_size, count)
    return count


def _iter_jsonl(path: Path):
    """Yield (record_index, line_number, parsed_object) for valid JSONL rows."""
    record_index = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            yield record_index, line_number, parsed
            record_index += 1


def _safe_len(value: object) -> int:
    """Return len(value) when value is a list, otherwise 0."""
    return len(value) if isinstance(value, list) else 0


def _to_int(value: object, default: int | None = None) -> int | None:
    """Convert value to integer when possible; otherwise return default."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _source_state(
    source_dir: Path,
    artifacts: SourceArtifacts,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a source-level summary with graceful incomplete-run handling."""
    jsonl_count = 0
    if artifacts.latest_jsonl is not None:
        jsonl_count = _count_jsonl_records(artifacts.latest_jsonl)

    status = "empty"
    record_count = 0
    metadata_record_count: int | None = None
    notes: list[str] = []

    if meta is not None:
        status = str(meta.get("status") or "unknown")
        metadata_record_count = _to_int(meta.get("record_count"), default=None)
        record_count = metadata_record_count if metadata_record_count is not None else jsonl_count

        if metadata_record_count is not None and artifacts.latest_jsonl is not None:
            if metadata_record_count != jsonl_count:
                notes.append("metadata record_count does not match current JSONL line count")
    elif artifacts.latest_jsonl is not None:
        status = "in_progress_or_interrupted"
        record_count = jsonl_count
        notes.append(
            "metadata file is missing; source may still be running or previous run ended early"
        )

    return {
        "name": source_dir.name,
        "status": status,
        "record_count": record_count,
        "jsonl_record_count": jsonl_count,
        "metadata_record_count": metadata_record_count,
        "latest_jsonl": artifacts.latest_jsonl.name if artifacts.latest_jsonl else None,
        "latest_meta": artifacts.latest_meta.name if artifacts.latest_meta else None,
        "jsonl_path": str(artifacts.latest_jsonl.resolve()) if artifacts.latest_jsonl else None,
        "meta_path": str(artifacts.latest_meta.resolve()) if artifacts.latest_meta else None,
        "notes": notes,
        "meta": meta,
    }


def _source_summary(run_dir: Path, source_name: str) -> dict[str, Any] | None:
    """Return one source summary object or None if source directory is missing."""
    source_dir = run_dir / source_name
    if not source_dir.is_dir():
        return None

    artifacts = _latest_artifacts(source_dir)
    meta = _read_json(artifacts.latest_meta) if artifacts.latest_meta else None
    return _source_state(source_dir, artifacts, meta)


def _list_runs(datasets_root: Path) -> list[dict[str, Any]]:
    """List dataset-run directories under datasets root."""
    if not datasets_root.exists() or not datasets_root.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for run_dir in sorted(datasets_root.iterdir()):
        if not run_dir.is_dir():
            continue
        source_dirs = [child for child in run_dir.iterdir() if child.is_dir()]
        results.append(
            {
                "name": run_dir.name,
                "path": str(run_dir.resolve()),
                "source_count": len(source_dirs),
            }
        )
    return results


def _list_sources(run_dir: Path) -> list[dict[str, Any]]:
    """List source summaries for one dataset-run directory."""
    if not run_dir.exists() or not run_dir.is_dir():
        return []

    sources: list[dict[str, Any]] = []
    for source_dir in sorted(run_dir.iterdir()):
        if not source_dir.is_dir():
            continue
        artifacts = _latest_artifacts(source_dir)
        meta = _read_json(artifacts.latest_meta) if artifacts.latest_meta else None
        sources.append(_source_state(source_dir, artifacts, meta))
    return sources


def _record_preview(index: int, line_number: int, record: dict[str, Any]) -> dict[str, Any]:
    """Build compact row payload for table rendering."""
    identifier_preview: list[str] = []
    for key in ("cve_ids", "ghsa_ids", "cwe_ids"):
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    identifier_preview.append(text)
                if len(identifier_preview) >= 6:
                    break
        if len(identifier_preview) >= 6:
            break

    description = str(record.get("description") or record.get("summary") or "").strip()
    compact = " ".join(description.split())

    procedure = record.get("procedure") if isinstance(record.get("procedure"), dict) else {}

    return {
        "index": index,
        "line_number": line_number,
        "record_uid": record.get("record_uid"),
        "source_record_id": record.get("source_record_id"),
        "title": record.get("title"),
        "vuln_status": record.get("vuln_status"),
        "published_at_utc": record.get("published_at_utc"),
        "modified_at_utc": record.get("modified_at_utc"),
        "identifier_preview": identifier_preview,
        "description_preview": compact[:240] + ("..." if len(compact) > 240 else ""),
        "reference_count": _safe_len(record.get("references")),
        "artifact_count": _safe_len(record.get("exploit_artifacts")),
        "tag_count": _safe_len(record.get("tags")),
        "procedure": {
            "steps": _safe_len(procedure.get("steps")),
            "commands": _safe_len(procedure.get("commands")),
            "payloads": _safe_len(procedure.get("payloads")),
        },
    }


def _records_page(
    jsonl_path: Path,
    *,
    offset: int,
    limit: int,
    query: str,
) -> dict[str, Any]:
    """Return paginated record previews with optional simple full-text filter."""
    offset = max(0, offset)
    limit = max(1, min(limit, 200))
    query_text = query.strip().lower()

    records: list[dict[str, Any]] = []
    has_more = False

    total_records = _count_jsonl_records(jsonl_path)

    if query_text:
        matched_count = 0
        for index, line_number, record in _iter_jsonl(jsonl_path):
            blob = json.dumps(record, ensure_ascii=False).lower()
            if query_text not in blob:
                continue

            if matched_count < offset:
                matched_count += 1
                continue

            if len(records) >= limit:
                has_more = True
                break

            records.append(_record_preview(index, line_number, record))
            matched_count += 1

        return {
            "offset": offset,
            "limit": limit,
            "query": query,
            "total_records": total_records,
            "returned": len(records),
            "has_more": has_more,
            "filtered": True,
            "records": records,
        }

    for index, line_number, record in _iter_jsonl(jsonl_path):
        if index < offset:
            continue
        if len(records) >= limit:
            has_more = True
            break
        records.append(_record_preview(index, line_number, record))

    return {
        "offset": offset,
        "limit": limit,
        "query": query,
        "total_records": total_records,
        "returned": len(records),
        "has_more": has_more,
        "filtered": False,
        "records": records,
    }


def _record_by_index(jsonl_path: Path, index: int) -> dict[str, Any] | None:
    """Fetch one full JSON object by record index from a JSONL file."""
    if index < 0:
        return None
    for current_index, line_number, record in _iter_jsonl(jsonl_path):
        if current_index == index:
            return {
                "index": current_index,
                "line_number": line_number,
                "record": record,
            }
    return None


class DatasetViewerServer(ThreadingHTTPServer):
    """HTTP server carrying immutable runtime configuration for the handler."""

    def __init__(
        self,
        server_address: tuple[str, int],
        datasets_root: Path,
        static_root: Path,
    ) -> None:
        super().__init__(server_address, DatasetViewerHandler)
        self.datasets_root = datasets_root.resolve()
        self.static_root = static_root.resolve()


class DatasetViewerHandler(BaseHTTPRequestHandler):
    """Serve viewer API and static assets."""

    server: DatasetViewerServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        self._handle_static(parsed.path)

    def _handle_api(self, parsed) -> None:
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)

        if parts == ["api", "health"]:
            self._send_json(
                {
                    "ok": True,
                    "datasets_root": str(self.server.datasets_root),
                    "static_root": str(self.server.static_root),
                }
            )
            return

        if parts in (["api", "runs"], ["api", "benchmarks"]):
            runs = _list_runs(self.server.datasets_root)
            self._send_json(
                {
                    "datasets_root": str(self.server.datasets_root),
                    "runs": runs,
                    "benchmarks": runs,
                }
            )
            return

        # /api/runs/<run>/sources
        if len(parts) == 4 and parts[1] in {"runs", "benchmarks"} and parts[3] == "sources":
            run_name = parts[2]
            run_dir = self.server.datasets_root / run_name
            if not run_dir.is_dir():
                self._send_error_json(HTTPStatus.NOT_FOUND, "dataset run not found")
                return
            self._send_json(
                {
                    "run": run_name,
                    "benchmark": run_name,
                    "sources": _list_sources(run_dir),
                }
            )
            return

        # /api/runs/<run>/sources/<source>/records
        if (
            len(parts) == 6
            and parts[1] in {"runs", "benchmarks"}
            and parts[3] == "sources"
            and parts[5] == "records"
        ):
            run_name = parts[2]
            source_name = parts[4]
            run_dir = self.server.datasets_root / run_name
            summary = _source_summary(run_dir, source_name)
            if summary is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "source not found")
                return

            jsonl_name = summary.get("latest_jsonl")
            if not isinstance(jsonl_name, str):
                self._send_json(
                    {
                        "run": run_name,
                        "benchmark": run_name,
                        "source": source_name,
                        "summary": summary,
                        "records": {
                            "offset": 0,
                            "limit": 0,
                            "query": "",
                            "total_records": 0,
                            "returned": 0,
                            "has_more": False,
                            "filtered": False,
                            "records": [],
                        },
                    }
                )
                return

            jsonl_path = run_dir / source_name / jsonl_name
            offset = _to_int(query.get("offset", ["0"])[0], default=0) or 0
            limit = _to_int(query.get("limit", ["50"])[0], default=50) or 50
            text_query = str(query.get("q", [""])[0])

            self._send_json(
                {
                    "run": run_name,
                    "benchmark": run_name,
                    "source": source_name,
                    "summary": summary,
                    "records": _records_page(
                        jsonl_path,
                        offset=offset,
                        limit=limit,
                        query=text_query,
                    ),
                }
            )
            return

        # /api/runs/<run>/sources/<source>/record?index=<n>
        if (
            len(parts) == 6
            and parts[1] in {"runs", "benchmarks"}
            and parts[3] == "sources"
            and parts[5] == "record"
        ):
            run_name = parts[2]
            source_name = parts[4]
            run_dir = self.server.datasets_root / run_name
            summary = _source_summary(run_dir, source_name)
            if summary is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "source not found")
                return

            jsonl_name = summary.get("latest_jsonl")
            if not isinstance(jsonl_name, str):
                self._send_error_json(HTTPStatus.NOT_FOUND, "source has no JSONL output yet")
                return

            index = _to_int(query.get("index", ["-1"])[0], default=-1)
            if index is None or index < 0:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "index query parameter must be a non-negative integer",
                )
                return

            jsonl_path = run_dir / source_name / jsonl_name
            payload = _record_by_index(jsonl_path, index)
            if payload is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "record index not found")
                return

            self._send_json(
                {
                    "run": run_name,
                    "benchmark": run_name,
                    "source": source_name,
                    "summary": summary,
                    "record": payload,
                }
            )
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, "unknown API route")

    def _handle_static(self, path: str) -> None:
        if path in {"", "/"}:
            self._serve_file(self.server.static_root / "index.html")
            return

        if path.startswith("/static/"):
            relative = Path(path.removeprefix("/static/")).as_posix().lstrip("/")
            target = self.server.static_root / relative
            self._serve_file(target)
            return

        # Fallback to SPA entry for unknown non-API routes.
        self._serve_file(self.server.static_root / "index.html")

    def _serve_file(self, target: Path) -> None:
        static_root = self.server.static_root.resolve()
        try:
            resolved = target.resolve()
        except FileNotFoundError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "file not found")
            return

        if not resolved.is_file() or not resolved.is_relative_to(static_root):
            self._send_error_json(HTTPStatus.NOT_FOUND, "file not found")
            return

        content_type, _ = mimetypes.guess_type(str(resolved))
        body = resolved.read_bytes()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message, "status": status.value}, status=status)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep server logs concise while still visible during local development.
        print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")


def parse_args() -> argparse.Namespace:
    """Parse runtime arguments for host, port, and datasets root."""
    parser = argparse.ArgumentParser(description="Dataset viewer server")
    parser.add_argument(
        "--datasets-root",
        default=str(DEFAULT_DATASETS_ROOT),
        help="Path to dataset-run output root (default: datasets/cybersecurity_records)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8710, help="Bind port (default: 8710)")
    return parser.parse_args()


def main() -> None:
    """Run the standalone dataset viewer server."""
    args = parse_args()
    datasets_root = Path(args.datasets_root).resolve()

    if not STATIC_ROOT.exists():
        raise SystemExit(f"Static directory is missing: {STATIC_ROOT}")

    server = DatasetViewerServer(
        (args.host, args.port),
        datasets_root=datasets_root,
        static_root=STATIC_ROOT,
    )

    print("Dataset viewer server started")
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  Datasets root: {datasets_root}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dataset viewer server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
