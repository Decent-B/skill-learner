"""Public normalization API."""

from skill_learner.normalization.models import (
    NormalizedCodeBlock,
    NormalizedDocument,
    NormalizedSection,
)
from skill_learner.normalization.normalize import (
    load_manifest_record,
    normalize_manifest_record,
    normalize_text,
    write_normalized_document,
)

__all__ = [
    "NormalizedCodeBlock",
    "NormalizedDocument",
    "NormalizedSection",
    "load_manifest_record",
    "normalize_manifest_record",
    "normalize_text",
    "write_normalized_document",
]
