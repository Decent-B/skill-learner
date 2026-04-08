"""Persistence helpers for raw ingestion outputs and manifests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from skill_learner.models import ManifestRecord

_SOURCE_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _validate_source_id(source_id: str) -> None:
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError(f"invalid source_id: {source_id}")


def raw_text_path_for(source_id: str, raw_dir: Path) -> Path:
    _validate_source_id(source_id)
    return (raw_dir / f"{source_id}.txt").resolve()


def manifest_path_for(source_id: str, manifest_dir: Path) -> Path:
    _validate_source_id(source_id)
    return (manifest_dir / f"{source_id}.json").resolve()


def write_raw_text(source_id: str, text: str, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_text_path_for(source_id=source_id, raw_dir=raw_dir)
    raw_path.write_text(text, encoding="utf-8")
    return raw_path


def write_manifest(record: ManifestRecord, manifest_dir: Path) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_path_for(source_id=record.source_id, manifest_dir=manifest_dir)
    serialized = json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True)
    path.write_text(serialized + "\n", encoding="utf-8")
    return path
