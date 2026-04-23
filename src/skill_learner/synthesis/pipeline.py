"""End-to-end pipeline for HackerOne-driven web exploit skill packages."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from skill_learner.models import CybersecurityRecord, DataSource

from .cwe_catalog import (
    GENERAL_OBSERVATION_SKILL_SLUG,
    SKILL_AUTHORING_GUIDANCE_SLUG,
    WEB_VULNERABILITY_CATEGORIES,
    VulnerabilityCategory,
    category_by_slug,
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
from .openai_client import OpenAIChatClient, OpenAIChatError, parse_json_object

AUTHORING_REFERENCE_URLS: tuple[str, ...] = (
    "https://agentskills.io/specification",
    "https://agentskills.io/skill-creation/optimizing-descriptions",
    "https://platform.openai.com/docs/guides/structured-outputs",
    "https://platform.openai.com/docs/guides/prompt-engineering/strategy-guidance",
    "https://platform.openai.com/docs/guides/function-calling",
    "https://platform.openai.com/docs/api-reference/chat/create-chat-completion",
    "https://platform.openai.com/docs/guides/prompt-caching/prompt-caching",
    "https://cwe.mitre.org/top25/archive/2024/2024_top25_list.html",
    "https://cwe.mitre.org/data/slices/1003.html",
)

_MAX_RECORD_TEXT_CHARS = 4000
_MAX_MESSAGES_TEXT_CHARS = 12000


class SkillPipelineError(RuntimeError):
    """Raised when the synthesis pipeline cannot safely continue."""


def run_hackerone_skill_package_pipeline(
    *,
    output_root: Path,
    package_name: str,
    benchmark_id: str,
    dataset_root: Path,
    hackerone_jsonl_path: Path | None,
    line_indices: list[int],
    record_keys: list[str],
    max_records: int,
    mode: SynthesisMode,
    openai_api_key: str,
    openai_model: str,
    openai_temperature: float,
    validation_enabled: bool,
    max_validation_attempts: int,
    console: Console,
) -> SynthesisRunSummary:
    """Generate a skill package from selected HackerOne records."""
    if validation_enabled and _resolve_validator_command() is None:
        raise SkillPipelineError(
            "Skill validation is enabled but `agentskills` was not found in PATH. "
            "Install `skills-ref` or run with validation disabled."
        )

    jsonl_path = (
        hackerone_jsonl_path
        if hackerone_jsonl_path is not None
        else resolve_latest_hackerone_jsonl(dataset_root=dataset_root, benchmark_id=benchmark_id)
    )
    all_records = load_hackerone_records(jsonl_path=jsonl_path)
    selections = select_hackerone_records(
        records=all_records,
        line_indices=line_indices,
        record_keys=record_keys,
        max_records=max_records,
        allow_empty=mode is SynthesisMode.BOOTSTRAP_ONLY,
    )

    started_at = datetime.now(UTC)
    package_dir = output_root / package_name
    run_dir = package_dir / "_runs" / started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    run_config = SynthesisRunConfig(
        package_name=package_name,
        mode=mode,
        benchmark_id=benchmark_id,
        hackerone_jsonl_path=str(jsonl_path.resolve()),
        line_indices=line_indices,
        record_keys=record_keys,
        max_records=max_records,
        model=openai_model,
        temperature=openai_temperature,
        validation_enabled=validation_enabled,
        max_validation_attempts=max_validation_attempts,
    )
    _write_json(run_dir / "run_config.json", run_config.model_dump(mode="json"))
    _write_json(
        run_dir / "selected_records.json",
        [selection.model_dump(mode="json") for selection in selections],
    )

    _render_run_header(
        console=console,
        run_config=run_config,
        package_dir=package_dir,
        run_dir=run_dir,
        selections=selections,
    )

    traces: list[LLMTraceEntry] = []
    edit_outcomes: list[SkillEditOutcome] = []
    bootstrap_created_count = 0

    client = OpenAIChatClient(
        api_key=openai_api_key,
        model=openai_model,
        temperature=openai_temperature,
    )
    try:
        _write_authoring_guidance_skill(package_dir=package_dir)
        bootstrap_created_count += bootstrap_missing_skills(
            package_dir=package_dir,
            client=client,
            traces=traces,
            validation_enabled=validation_enabled,
            max_validation_attempts=max_validation_attempts,
            console=console,
        )

        if mode is SynthesisMode.FULL:
            edit_outcomes.extend(
                process_selected_records(
                    selections=selections,
                    records=all_records,
                    package_dir=package_dir,
                    client=client,
                    traces=traces,
                    validation_enabled=validation_enabled,
                    max_validation_attempts=max_validation_attempts,
                    console=console,
                )
            )
    finally:
        client.close()

    _write_json(
        run_dir / "skill_edit_outcomes.json",
        [outcome.model_dump(mode="json") for outcome in edit_outcomes],
    )
    _write_jsonl(run_dir / "llm_traces.jsonl", [trace.model_dump(mode="json") for trace in traces])

    summary = build_run_summary(
        started_at_utc=started_at,
        ended_at_utc=datetime.now(UTC),
        package_dir=package_dir,
        mode=mode,
        selected_records=len(selections),
        bootstrap_created_skills=bootstrap_created_count,
        edit_outcomes=edit_outcomes,
        traces=traces,
    )
    _write_json(run_dir / "run_summary.json", summary.model_dump(mode="json"))
    _render_run_footer(console=console, summary=summary, run_dir=run_dir)
    return summary


def resolve_latest_hackerone_jsonl(*, dataset_root: Path, benchmark_id: str) -> Path:
    """Resolve latest HackerOne JSONL snapshot for one benchmark."""
    source_dir = dataset_root / benchmark_id / DataSource.HACKERONE_REPORTS.value
    if not source_dir.exists():
        raise SkillPipelineError(f"HackerOne source directory not found: {source_dir}")

    jsonl_files = sorted(source_dir.glob("*.jsonl"))
    if not jsonl_files:
        raise SkillPipelineError(f"No HackerOne JSONL files found under: {source_dir}")
    return jsonl_files[-1]


def load_hackerone_records(*, jsonl_path: Path) -> list[CybersecurityRecord]:
    """Load and validate HackerOne records from one JSONL file."""
    records: list[CybersecurityRecord] = []
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SkillPipelineError(f"Invalid JSON at {jsonl_path}:{line_number}") from exc

        try:
            record = CybersecurityRecord.model_validate(payload)
        except Exception as exc:
            raise SkillPipelineError(f"Invalid record at {jsonl_path}:{line_number}") from exc

        if record.source is not DataSource.HACKERONE_REPORTS:
            continue
        records.append(record)
    return records


def select_hackerone_records(
    *,
    records: list[CybersecurityRecord],
    line_indices: list[int],
    record_keys: list[str],
    max_records: int,
    allow_empty: bool,
) -> list[RecordSelection]:
    """Select records by 1-based line index and/or record key."""
    normalized_line_indices = [index for index in line_indices if index >= 1]
    normalized_record_keys = [key.strip() for key in record_keys if key.strip()]

    if not normalized_line_indices and not normalized_record_keys and not allow_empty:
        raise SkillPipelineError(
            "No input records selected. Provide --line-index and/or --record-key, "
            "or use --bootstrap-only."
        )

    key_set = set(normalized_record_keys)
    selected: OrderedDict[int, RecordSelection] = OrderedDict()

    if normalized_line_indices:
        for index in normalized_line_indices:
            if index > len(records):
                raise SkillPipelineError(
                    f"Line index {index} is out of range for {len(records)} HackerOne records."
                )
            selected[index] = _to_selection(index=index, record=records[index - 1])

    if key_set:
        for index, record in enumerate(records, start=1):
            if record.record_uid in key_set or record.source_record_id in key_set:
                selected[index] = _to_selection(index=index, record=record)

    selections = list(selected.values())[:max_records]
    if not selections and not allow_empty:
        raise SkillPipelineError(
            "Provided keys/indices did not match any HackerOne records in input JSONL."
        )
    return selections


def bootstrap_missing_skills(
    *,
    package_dir: Path,
    client: OpenAIChatClient,
    traces: list[LLMTraceEntry],
    validation_enabled: bool,
    max_validation_attempts: int,
    console: Console,
) -> int:
    """Create missing base skills (general + vulnerability categories)."""
    created_count = 0
    target_categories = list(WEB_VULNERABILITY_CATEGORIES)

    console.print(
        Panel.fit(
            f"Bootstrapping missing skills in [bold]{package_dir}[/bold]\n"
            f"Targets: general + {len(target_categories)} vulnerability categories",
            title="Bootstrap",
            border_style="cyan",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Creating base skills", total=1 + len(target_categories))

        general_skill_path = package_dir / GENERAL_OBSERVATION_SKILL_SLUG / "SKILL.md"
        if not general_skill_path.exists():
            markdown = generate_or_repair_skill_markdown(
                skill_slug=GENERAL_OBSERVATION_SKILL_SLUG,
                existing_markdown=None,
                generation_messages=_base_general_skill_messages(),
                client=client,
                traces=traces,
                step_type="bootstrap_general",
                validation_enabled=validation_enabled,
                max_validation_attempts=max_validation_attempts,
                skill_dir=general_skill_path.parent,
                console=console,
            )
            _write_text(general_skill_path, markdown)
            created_count += 1
        progress.advance(task_id)

        for category in target_categories:
            skill_path = package_dir / category.slug / "SKILL.md"
            if not skill_path.exists():
                markdown = generate_or_repair_skill_markdown(
                    skill_slug=category.slug,
                    existing_markdown=None,
                    generation_messages=_base_category_skill_messages(category),
                    client=client,
                    traces=traces,
                    step_type="bootstrap_category",
                    validation_enabled=validation_enabled,
                    max_validation_attempts=max_validation_attempts,
                    skill_dir=skill_path.parent,
                    console=console,
                )
                _write_text(skill_path, markdown)
                created_count += 1
            progress.advance(task_id)

    return created_count


def process_selected_records(
    *,
    selections: list[RecordSelection],
    records: list[CybersecurityRecord],
    package_dir: Path,
    client: OpenAIChatClient,
    traces: list[LLMTraceEntry],
    validation_enabled: bool,
    max_validation_attempts: int,
    console: Console,
) -> list[SkillEditOutcome]:
    """Process selected records and edit at most two skills per record."""
    outcomes: list[SkillEditOutcome] = []
    if not selections:
        return outcomes

    record_by_uid = {record.record_uid: record for record in records}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Applying records", total=len(selections))
        for selection in selections:
            record = record_by_uid.get(selection.record_uid)
            if record is None:
                raise SkillPipelineError(f"Selected record {selection.record_uid} is missing.")

            decision, classify_usage = classify_record_for_skill(
                record=record,
                client=client,
                traces=traces,
            )
            console.log(
                f"[bold]Record[/bold] {selection.source_record_id} -> "
                f"[cyan]{decision.vulnerability_skill_slug}[/cyan] "
                f"({decision.confidence})"
            )
            if classify_usage is not None:
                console.log(
                    "[blue]classify_record[/blue] "
                    f"(prompt={classify_usage.prompt_tokens}, "
                    f"completion={classify_usage.completion_tokens}, "
                    f"total={classify_usage.total_tokens})"
                )

            target_skill_slugs: list[str] = []
            if decision.should_edit_general_observation:
                target_skill_slugs.append(GENERAL_OBSERVATION_SKILL_SLUG)
            if decision.should_edit_vulnerability_skill:
                target_skill_slugs.append(decision.vulnerability_skill_slug)

            # Hard limit: at most 2 skill edits per record.
            target_skill_slugs = list(dict.fromkeys(target_skill_slugs))[:2]
            for skill_slug in target_skill_slugs:
                outcome = apply_record_to_skill(
                    record=record,
                    skill_slug=skill_slug,
                    package_dir=package_dir,
                    client=client,
                    traces=traces,
                    validation_enabled=validation_enabled,
                    max_validation_attempts=max_validation_attempts,
                    console=console,
                )
                outcomes.append(outcome)

            progress.advance(task_id)
    return outcomes


def classify_record_for_skill(
    *,
    record: CybersecurityRecord,
    client: OpenAIChatClient,
    traces: list[LLMTraceEntry],
) -> tuple[SkillDecision, TokenUsageSnapshot | None]:
    """Classify one record to a broad vulnerability skill category."""
    category_table = [
        {
            "slug": category.slug,
            "title": category.title,
            "summary": category.summary,
            "trigger_hints": list(category.trigger_hints),
        }
        for category in WEB_VULNERABILITY_CATEGORIES
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You classify web security reports into one broad vulnerability category. "
                "Return JSON only with keys: vulnerability_skill_slug, confidence, rationale, "
                "should_edit_general_observation, should_edit_vulnerability_skill."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "classify_hackerone_record",
                    "allowed_skill_slugs": [
                        category.slug for category in WEB_VULNERABILITY_CATEGORIES
                    ],
                    "categories": category_table,
                    "record": _record_digest(record),
                    "constraints": {
                        "prefer_broad_categories": True,
                        "max_specificity": "broad class only",
                        "always_edit_general_observation": True,
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]

    trace, parsed = _run_json_step(
        client=client,
        messages=messages,
        step_type="classify_record",
        record_uid=record.record_uid,
        target_skill_slug=None,
    )
    traces.append(trace)

    fallback_slug = infer_category_slug_from_record(record)
    try:
        decision = SkillDecision.model_validate(parsed)
    except Exception:
        return (
            SkillDecision(
                vulnerability_skill_slug=fallback_slug,
                confidence="low",
                rationale="Fallback heuristic used due to parse/validation error.",
                should_edit_general_observation=True,
                should_edit_vulnerability_skill=True,
            ),
            trace.usage,
        )

    if category_by_slug(decision.vulnerability_skill_slug) is None:
        decision = decision.model_copy(update={"vulnerability_skill_slug": fallback_slug})
    return decision, trace.usage


def apply_record_to_skill(
    *,
    record: CybersecurityRecord,
    skill_slug: str,
    package_dir: Path,
    client: OpenAIChatClient,
    traces: list[LLMTraceEntry],
    validation_enabled: bool,
    max_validation_attempts: int,
    console: Console,
) -> SkillEditOutcome:
    """Refactor one skill from one record and validate the result."""
    skill_dir = package_dir / skill_slug
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise SkillPipelineError(f"Skill not found for update: {skill_path}")

    existing = skill_path.read_text(encoding="utf-8")
    messages = _edit_skill_messages(
        skill_slug=skill_slug,
        current_markdown=existing,
        record=record,
    )
    updated = generate_or_repair_skill_markdown(
        skill_slug=skill_slug,
        existing_markdown=existing,
        generation_messages=messages,
        client=client,
        traces=traces,
        step_type="edit_skill",
        validation_enabled=validation_enabled,
        max_validation_attempts=max_validation_attempts,
        skill_dir=skill_dir,
        console=console,
        record_uid=record.record_uid,
    )
    _write_text(skill_path, updated)

    validation_attempts = 0
    validation_passed = True
    if validation_enabled:
        validation_attempts = 1
        validation_passed, _ = validate_skill(skill_dir=skill_dir)
    usage = _sum_usage_for_record_skill(
        traces=traces,
        record_uid=record.record_uid,
        skill_slug=skill_slug,
    )
    return SkillEditOutcome(
        record_uid=record.record_uid,
        skill_slug=skill_slug,
        validation_passed=validation_passed,
        validation_attempts=validation_attempts,
        usage=usage,
    )


def generate_or_repair_skill_markdown(
    *,
    skill_slug: str,
    existing_markdown: str | None,
    generation_messages: list[dict[str, str]],
    client: OpenAIChatClient,
    traces: list[LLMTraceEntry],
    step_type: str,
    validation_enabled: bool,
    max_validation_attempts: int,
    skill_dir: Path,
    console: Console,
    record_uid: str | None = None,
) -> str:
    """Generate skill markdown and optionally repair until validation passes."""
    markdown, usage = _run_markdown_step(
        client=client,
        messages=generation_messages,
        traces=traces,
        step_type=step_type,
        record_uid=record_uid,
        target_skill_slug=skill_slug,
    )
    console.log(
        f"[green]{step_type}[/green] -> {skill_slug} "
        + (
            f"(prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, "
            f"total={usage.total_tokens})"
        )
    )

    if not validation_enabled:
        return markdown

    for attempt in range(1, max_validation_attempts + 1):
        _write_text(skill_dir / "SKILL.md", markdown)
        valid, validation_output = validate_skill(skill_dir=skill_dir)
        if valid:
            return markdown
        if attempt == max_validation_attempts:
            raise SkillPipelineError(
                f"Validation failed for {skill_slug} after {max_validation_attempts} attempts.\n"
                f"{validation_output}"
            )

        repair_messages = _repair_skill_messages(
            skill_slug=skill_slug,
            broken_markdown=markdown,
            validation_error=validation_output,
            existing_markdown=existing_markdown,
        )
        markdown, repair_usage = _run_markdown_step(
            client=client,
            messages=repair_messages,
            traces=traces,
            step_type=f"{step_type}_repair",
            record_uid=record_uid,
            target_skill_slug=skill_slug,
        )
        console.log(
            f"[yellow]repair[/yellow] {skill_slug} "
            f"(prompt={repair_usage.prompt_tokens}, completion={repair_usage.completion_tokens}, "
            f"total={repair_usage.total_tokens})"
        )
    return markdown


def validate_skill(*, skill_dir: Path) -> tuple[bool, str]:
    """Validate one skill directory against Agent Skills specification."""
    command = _resolve_validator_command()
    if command is None:
        return False, "agentskills validator command is unavailable."

    completed = subprocess.run(
        [*command, "validate", str(skill_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    return completed.returncode == 0, output


def build_run_summary(
    *,
    started_at_utc: datetime,
    ended_at_utc: datetime,
    package_dir: Path,
    mode: SynthesisMode,
    selected_records: int,
    bootstrap_created_skills: int,
    edit_outcomes: list[SkillEditOutcome],
    traces: list[LLMTraceEntry],
) -> SynthesisRunSummary:
    """Aggregate usage and outcome counters into one summary payload."""
    usage_totals = TokenUsageSnapshot()
    validation_failures = sum(1 for outcome in edit_outcomes if not outcome.validation_passed)
    for trace in traces:
        if trace.usage is None:
            continue
        usage_totals = _add_usage(usage_totals, trace.usage)

    return SynthesisRunSummary(
        started_at_utc=started_at_utc,
        ended_at_utc=ended_at_utc,
        package_dir=str(package_dir.resolve()),
        mode=mode,
        selected_records=selected_records,
        bootstrap_created_skills=bootstrap_created_skills,
        edited_skills=len(edit_outcomes),
        total_prompt_tokens=usage_totals.prompt_tokens,
        total_completion_tokens=usage_totals.completion_tokens,
        total_tokens=usage_totals.total_tokens,
        total_cached_tokens=usage_totals.cached_tokens,
        total_reasoning_tokens=usage_totals.reasoning_tokens,
        traces_written=len(traces),
        validation_failures=validation_failures,
    )


def infer_category_slug_from_record(record: CybersecurityRecord) -> str:
    """Heuristic fallback mapping from record content to one category slug."""
    text = " ".join(
        [
            record.title,
            record.summary or "",
            record.description or "",
            " ".join(record.weaknesses),
            " ".join(record.tags),
            " ".join(record.procedure.steps),
            " ".join(record.procedure.payloads),
        ]
    ).lower()
    for category in WEB_VULNERABILITY_CATEGORIES:
        if any(hint.lower() in text for hint in category.trigger_hints):
            return category.slug
    return WEB_VULNERABILITY_CATEGORIES[0].slug


def _record_digest(record: CybersecurityRecord) -> dict[str, Any]:
    """Compact record digest used in model prompts and logs."""
    description = (record.description or "")[:_MAX_RECORD_TEXT_CHARS]
    return {
        "record_uid": record.record_uid,
        "source_record_id": record.source_record_id,
        "title": record.title,
        "summary": record.summary,
        "description": description,
        "weaknesses": record.weaknesses,
        "cwe_ids": record.cwe_ids,
        "aliases": record.aliases,
        "procedure": {
            "steps": record.procedure.steps[:12],
            "commands": record.procedure.commands[:12],
            "payloads": record.procedure.payloads[:12],
        },
        "references": [reference.url for reference in record.references[:10]],
    }


def _base_general_skill_messages() -> list[dict[str, str]]:
    category_routing = [
        {"slug": category.slug, "title": category.title}
        for category in WEB_VULNERABILITY_CATEGORIES
    ]
    payload = {
        "task": "create_base_general_observation_skill",
        "skill_slug": GENERAL_OBSERVATION_SKILL_SLUG,
        "routing_targets": category_routing,
        "requirements": {
            "format": "Agent Skills SKILL.md",
            "style": "concise, procedural, low-token",
            "focus": "guide observations, hypothesize attack surfaces, route to specific skills",
            "must_include": [
                "when to use",
                "observation checklist",
                "attack-surface hypothesis loop",
                "routing policy to specific vulnerability skills",
                "evidence recording contract",
            ],
        },
        "references": list(AUTHORING_REFERENCE_URLS),
    }
    return _markdown_generation_messages(payload)


def _base_category_skill_messages(category: VulnerabilityCategory) -> list[dict[str, str]]:
    payload = {
        "task": "create_base_specific_vulnerability_skill",
        "skill_slug": category.slug,
        "skill_title": category.title,
        "summary": category.summary,
        "cwe_ids": list(category.cwe_ids),
        "cwe_reference_urls": list(category.cwe_reference_urls),
        "trigger_hints": list(category.trigger_hints),
        "requirements": {
            "format": "Agent Skills SKILL.md",
            "style": "concise, practical, broad class (not narrow variant)",
            "must_include": [
                "when to use",
                "preconditions",
                "minimal verification sequence",
                "payload strategy guidance",
                "impact validation cues",
                "safe fallback and false-positive checks",
            ],
            "avoid": [
                "single-product hardcoding",
                "narrow exploit subtype naming",
                "long encyclopedic explanations",
            ],
        },
        "references": list(AUTHORING_REFERENCE_URLS),
    }
    return _markdown_generation_messages(payload)


def _edit_skill_messages(
    *,
    skill_slug: str,
    current_markdown: str,
    record: CybersecurityRecord,
) -> list[dict[str, str]]:
    payload = {
        "task": "refactor_skill_with_new_record",
        "skill_slug": skill_slug,
        "constraints": {
            "max_skills_affected": 2,
            "must_preserve_frontmatter_name": True,
            "maintain_broad_skill_scope": True,
            "concise_update_only": True,
        },
        "current_skill_markdown": current_markdown[:_MAX_MESSAGES_TEXT_CHARS],
        "record_digest": _record_digest(record),
        "references": list(AUTHORING_REFERENCE_URLS),
    }
    return _markdown_generation_messages(payload)


def _repair_skill_messages(
    *,
    skill_slug: str,
    broken_markdown: str,
    validation_error: str,
    existing_markdown: str | None,
) -> list[dict[str, str]]:
    payload = {
        "task": "repair_skill_to_pass_validation",
        "skill_slug": skill_slug,
        "validation_error": validation_error[:4000],
        "existing_skill_markdown": (existing_markdown or "")[:_MAX_MESSAGES_TEXT_CHARS],
        "broken_skill_markdown": broken_markdown[:_MAX_MESSAGES_TEXT_CHARS],
        "requirements": {
            "must_output_only": "fixed SKILL.md markdown",
            "must_pass": "Agent Skills validation constraints",
            "preserve_intent": True,
        },
        "references": list(AUTHORING_REFERENCE_URLS),
    }
    return _markdown_generation_messages(payload)


def _markdown_generation_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You write Agent Skills. Output only a valid SKILL.md markdown file with YAML "
                "frontmatter and concise body instructions. Do not output code fences."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]


def _run_markdown_step(
    *,
    client: OpenAIChatClient,
    messages: list[dict[str, str]],
    traces: list[LLMTraceEntry],
    step_type: str,
    record_uid: str | None,
    target_skill_slug: str | None,
) -> tuple[str, TokenUsageSnapshot]:
    trace_started = datetime.now(UTC)
    response = client.create_completion(messages=messages, require_json_object=False)
    trace = LLMTraceEntry(
        started_at_utc=trace_started,
        ended_at_utc=datetime.now(UTC),
        step_type=step_type,
        model=client.model,
        record_uid=record_uid,
        target_skill_slug=target_skill_slug,
        request_messages=messages,
        response_text=response.text,
        parsed_json=None,
        usage=response.usage,
        error=None,
    )
    traces.append(trace)
    return _sanitize_markdown_response(response.text), response.usage


def _run_json_step(
    *,
    client: OpenAIChatClient,
    messages: list[dict[str, str]],
    step_type: str,
    record_uid: str | None,
    target_skill_slug: str | None,
) -> tuple[LLMTraceEntry, dict[str, Any]]:
    trace_started = datetime.now(UTC)
    try:
        response = client.create_completion(messages=messages, require_json_object=True)
        parsed = parse_json_object(response.text)
        trace = LLMTraceEntry(
            started_at_utc=trace_started,
            ended_at_utc=datetime.now(UTC),
            step_type=step_type,
            model=client.model,
            record_uid=record_uid,
            target_skill_slug=target_skill_slug,
            request_messages=messages,
            response_text=response.text,
            parsed_json=parsed,
            usage=response.usage,
            error=None,
        )
        return trace, parsed
    except (OpenAIChatError, json.JSONDecodeError) as exc:
        trace = LLMTraceEntry(
            started_at_utc=trace_started,
            ended_at_utc=datetime.now(UTC),
            step_type=step_type,
            model=client.model,
            record_uid=record_uid,
            target_skill_slug=target_skill_slug,
            request_messages=messages,
            response_text="",
            parsed_json=None,
            usage=None,
            error=str(exc),
        )
        return trace, {}


def _resolve_validator_command() -> list[str] | None:
    direct = shutil.which("agentskills")
    if direct is not None:
        return [direct]
    return None


def _sanitize_markdown_response(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:markdown|md)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip() + "\n"


def _to_selection(*, index: int, record: CybersecurityRecord) -> RecordSelection:
    return RecordSelection(
        line_index_1_based=index,
        record_uid=record.record_uid,
        source_record_id=record.source_record_id,
        title=record.title,
        summary=record.summary,
    )


def _sum_usage_for_record_skill(
    *,
    traces: list[LLMTraceEntry],
    record_uid: str,
    skill_slug: str,
) -> TokenUsageSnapshot:
    usage = TokenUsageSnapshot()
    for trace in traces:
        if trace.record_uid != record_uid:
            continue
        if trace.target_skill_slug != skill_slug:
            continue
        if trace.usage is None:
            continue
        usage = _add_usage(usage, trace.usage)
    return usage


def _add_usage(left: TokenUsageSnapshot, right: TokenUsageSnapshot) -> TokenUsageSnapshot:
    return TokenUsageSnapshot(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
        cached_tokens=left.cached_tokens + right.cached_tokens,
        reasoning_tokens=left.reasoning_tokens + right.reasoning_tokens,
    )


def _write_authoring_guidance_skill(*, package_dir: Path) -> None:
    guidance_dir = package_dir / SKILL_AUTHORING_GUIDANCE_SLUG
    guidance_dir.mkdir(parents=True, exist_ok=True)
    skill_path = guidance_dir / "SKILL.md"
    if skill_path.exists():
        return

    content = "\n".join(
        [
            "---",
            f"name: {SKILL_AUTHORING_GUIDANCE_SLUG}",
            "description: >-",
            "  Internal guidance for generating and refactoring skill folders from",
            "  vulnerability records while keeping SKILL.md concise and valid.",
            "---",
            "",
            "# Purpose",
            "- Keep generated skills broad, reusable, and validation-friendly.",
            "- Prioritize trigger clarity and procedural test/observation loops.",
            "",
            "# Authoring Rules",
            "1. Keep frontmatter name stable and lowercase-hyphenated.",
            "2. Keep descriptions concise and trigger-focused.",
            "3. Prefer short default path plus fallback path.",
            "4. Move heavy detail to references/assets when needed.",
            "5. Preserve one concern per skill and avoid variant over-specialization.",
            "",
            "# Reference Sources",
            *[f"- {url}" for url in AUTHORING_REFERENCE_URLS],
            "",
        ]
    )
    _write_text(skill_path, content + "\n")


def _render_run_header(
    *,
    console: Console,
    run_config: SynthesisRunConfig,
    package_dir: Path,
    run_dir: Path,
    selections: list[RecordSelection],
) -> None:
    summary_table = Table(title="Web Exploit Skill Package Run")
    summary_table.add_column("Field")
    summary_table.add_column("Value")
    summary_table.add_row("package", run_config.package_name)
    summary_table.add_row("mode", run_config.mode.value)
    summary_table.add_row("model", run_config.model)
    summary_table.add_row("benchmark", run_config.benchmark_id)
    summary_table.add_row("hackerone_jsonl", run_config.hackerone_jsonl_path)
    summary_table.add_row("selected_records", str(len(selections)))
    summary_table.add_row("output_dir", str(package_dir.resolve()))
    summary_table.add_row("run_log_dir", str(run_dir.resolve()))
    console.print(summary_table)

    if selections:
        selection_table = Table(title="Selected Records")
        selection_table.add_column("Line")
        selection_table.add_column("Record ID")
        selection_table.add_column("UID")
        selection_table.add_column("Title")
        for selection in selections[:40]:
            selection_table.add_row(
                str(selection.line_index_1_based),
                selection.source_record_id,
                selection.record_uid,
                selection.title[:80],
            )
        if len(selections) > 40:
            selection_table.add_row(
                "...",
                "...",
                "...",
                f"{len(selections) - 40} additional records",
            )
        console.print(selection_table)


def _render_run_footer(
    *,
    console: Console,
    summary: SynthesisRunSummary,
    run_dir: Path,
) -> None:
    token_table = Table(title="Token Usage Totals")
    token_table.add_column("Metric")
    token_table.add_column("Value")
    token_table.add_row("prompt_tokens", str(summary.total_prompt_tokens))
    token_table.add_row("completion_tokens", str(summary.total_completion_tokens))
    token_table.add_row("total_tokens", str(summary.total_tokens))
    token_table.add_row("cached_tokens", str(summary.total_cached_tokens))
    token_table.add_row("reasoning_tokens", str(summary.total_reasoning_tokens))
    console.print(token_table)

    console.print(
        Panel.fit(
            f"Run complete.\nSummary: [bold]{run_dir / 'run_summary.json'}[/bold]\n"
            f"Traces: [bold]{run_dir / 'llm_traces.jsonl'}[/bold]",
            title="Artifacts",
            border_style="green",
        )
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    lines = [json.dumps(payload, sort_keys=True) for payload in payloads]
    _write_text(path, ("\n".join(lines) + "\n") if lines else "")
