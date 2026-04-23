"""Synthesis package for skill generation from cybersecurity records."""

from .cwe_catalog import (
    GENERAL_OBSERVATION_SKILL_SLUG,
    SKILL_AUTHORING_GUIDANCE_SLUG,
    WEB_VULNERABILITY_CATEGORIES,
    VulnerabilityCategory,
)
from .models import (
    LLMTraceEntry,
    RecordSelection,
    SkillDecision,
    SkillEditOutcome,
    SynthesisMode,
    SynthesisRunConfig,
    SynthesisRunSummary,
    TokenUsageSnapshot,
)
from .pipeline import (
    SkillPipelineError,
    load_hackerone_records,
    resolve_latest_hackerone_jsonl,
    run_hackerone_skill_package_pipeline,
    select_hackerone_records,
)

__all__ = [
    "GENERAL_OBSERVATION_SKILL_SLUG",
    "SKILL_AUTHORING_GUIDANCE_SLUG",
    "LLMTraceEntry",
    "RecordSelection",
    "SkillDecision",
    "SkillEditOutcome",
    "SkillPipelineError",
    "SynthesisMode",
    "SynthesisRunConfig",
    "SynthesisRunSummary",
    "TokenUsageSnapshot",
    "VulnerabilityCategory",
    "WEB_VULNERABILITY_CATEGORIES",
    "load_hackerone_records",
    "resolve_latest_hackerone_jsonl",
    "run_hackerone_skill_package_pipeline",
    "select_hackerone_records",
]
