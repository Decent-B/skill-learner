"""Deterministic synthesis of Agent Skill packages from extraction previews."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from skill_learner.extraction import StepConfidence

from .models import PreviewPayload, SelectedStep, SkillMetadata, SkillSynthesisResult

_SKILL_NAME_SAFE_RE = re.compile(r"[^a-z0-9-]+")
_SPACE_RE = re.compile(r"\s+")
_NOISE_EXACT = {
    "created",
    "opened",
    "labeled",
    "closed",
    "edited",
    "assigned",
    "document",
}
_PLACEHOLDER_MARKERS = ("taskname", "option-name", "[...]", "...")
_TAG_WEIGHT = {
    "build_cmd": 50,
    "dependency_fix": 40,
    "rerun_strategy": 30,
    "diagnostic_flag": 20,
    "ci_yaml": 10,
}
_CONFIDENCE_WEIGHT = {
    StepConfidence.HIGH: 300,
    StepConfidence.MEDIUM: 200,
    StepConfidence.LOW: 100,
}
_DEFAULT_COMPATIBILITY = (
    "Designed for CI build-fix tasks with git, shell access, and dependency "
    "network access for Maven, Gradle, or Bazel workflows."
)
_DEFAULT_DESCRIPTION = (
    "Use this skill when fixing failed CI or local build pipelines for Java/"
    "Google-style repositories. It provides a deterministic workflow for "
    "diagnosing build flags, dependency configuration, workflow YAML issues, "
    "and rerun strategies."
)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        stripped = item.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        ordered.append(stripped)
    return ordered


def suggest_skill_name(benchmark_id: str) -> str:
    """Generate a deterministic, spec-compliant skill name from benchmark id."""
    seed = benchmark_id.strip().lower().replace("_", "-")
    normalized = _SKILL_NAME_SAFE_RE.sub("-", seed)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        normalized = "generated-skill"

    candidate = f"{normalized}-repair"
    if len(candidate) > 64:
        candidate = candidate[:64].rstrip("-")
    if "--" in candidate:
        candidate = re.sub(r"-{2,}", "-", candidate).strip("-")
    return candidate


def load_preview_payload(preview_json: Path) -> PreviewPayload:
    """Load and validate phase-2 preview payload."""
    payload = json.loads(preview_json.read_text(encoding="utf-8"))
    return PreviewPayload.model_validate(payload)


def _is_noise_text(text: str, confidence: StepConfidence, tags: list[str]) -> bool:
    compact = _SPACE_RE.sub(" ", text.strip())
    lowered = compact.lower()
    if lowered in _NOISE_EXACT:
        return True
    if compact.startswith("name: "):
        return True
    if confidence is StepConfidence.LOW and not tags:
        if len(lowered) <= 20:
            return True
        if len(lowered.split()) <= 3:
            return True
    if len(compact) > 260 and "build_cmd" not in tags and "dependency_fix" not in tags:
        return True
    if "build_cmd" in tags:
        if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
            return True
        # Keep concrete commands; drop placeholder command templates.
        if "[" in compact and "]" in compact:
            return True
    return False


def _tag_score(tags: list[str]) -> int:
    return sum(_TAG_WEIGHT.get(tag, 0) for tag in tags)


def select_candidate_steps(payload: PreviewPayload, max_steps: int = 24) -> list[SelectedStep]:
    """Select and rank useful steps from a preview payload deterministically."""
    ranked: list[tuple[tuple[int, int, str, int, str], SelectedStep]] = []
    for item in payload.items:
        if item.status != "success" or item.steps is None:
            continue
        for index, preview_step in enumerate(item.steps):
            if _is_noise_text(
                preview_step.text,
                confidence=preview_step.confidence,
                tags=preview_step.tags,
            ):
                continue
            selected = SelectedStep(
                source_item_id=item.id,
                source_id=preview_step.source_id,
                text=preview_step.text.strip(),
                tags=preview_step.tags,
                confidence=preview_step.confidence,
                span=preview_step.span,
                preconditions=preview_step.preconditions,
                postconditions=preview_step.postconditions,
            )
            confidence_score = _CONFIDENCE_WEIGHT[preview_step.confidence]
            # Ranking order:
            # 1) confidence
            # 2) important tags
            # 3) stable source/order/text tie-breakers
            key = (
                -confidence_score,
                -_tag_score(preview_step.tags),
                selected.source_id,
                index,
                selected.text.lower(),
            )
            ranked.append((key, selected))

    ranked.sort(key=lambda entry: entry[0])

    unique_texts: set[str] = set()
    source_quota: dict[str, int] = {}
    selected_steps: list[SelectedStep] = []
    for _, step in ranked:
        canonical = _SPACE_RE.sub(" ", step.text).lower()
        if canonical in unique_texts:
            continue
        if source_quota.get(step.source_item_id, 0) >= 4:
            # Prevent one verbose source from dominating the generated skill.
            continue
        unique_texts.add(canonical)
        source_quota[step.source_item_id] = source_quota.get(step.source_item_id, 0) + 1
        selected_steps.append(step)
        if len(selected_steps) >= max_steps:
            break
    return selected_steps


def _render_frontmatter(metadata: SkillMetadata) -> str:
    lines = [
        "---",
        f"name: {metadata.name}",
        f"description: {metadata.description}",
    ]
    if metadata.compatibility is not None:
        lines.append(f"compatibility: {metadata.compatibility}")
    lines.append("---")
    return "\n".join(lines)


def _render_skill_body(steps: list[SelectedStep]) -> str:
    # Pull prerequisites from extracted procedural constraints first, then
    # fall back to concise defaults for minimum usable guidance.
    prereqs = _dedupe_keep_order(
        [pre for step in steps for pre in step.preconditions]
        or [
            "Repository checkout and access to CI workflow files.",
            "Build tooling available (Maven, Gradle, or Bazel).",
            "Network and credentials configured for dependency downloads.",
        ]
    )

    build_steps = [
        step
        for step in steps
        if any(tag in step.tags for tag in ("build_cmd", "dependency_fix", "ci_yaml"))
    ][:10]
    if not build_steps:
        build_steps = steps[:10]

    rerun_steps = [
        step
        for step in steps
        if any(tag in step.tags for tag in ("rerun_strategy", "diagnostic_flag"))
    ][:8]
    if not rerun_steps:
        rerun_steps = [step for step in steps if step.confidence is not StepConfidence.LOW][:6]

    failure_hints = _dedupe_keep_order(
        [post for step in steps for post in step.postconditions]
        or [
            "Capture full logs and compare with the last known passing run.",
            "Isolate dependency, workflow syntax, and module-specific failures separately.",
        ]
    )

    lines: list[str] = []
    lines.append("## When To Use")
    lines.append(
        "Use this skill when a CI/build pipeline fails in Java or Google-style repositories and "
        "you need a deterministic fix flow for workflow, dependency, and build-flag issues."
    )
    lines.append("")
    lines.append("## Prerequisites")
    for prerequisite in prereqs:
        lines.append(f"- {prerequisite}")
    lines.append("")
    lines.append("## Build-Fix Procedure")
    for index, step in enumerate(build_steps, start=1):
        lines.append(f"{index}. {step.text}")
    lines.append("")
    lines.append("## Rerun And Verification")
    for index, step in enumerate(rerun_steps, start=1):
        lines.append(f"{index}. {step.text}")
    lines.append("")
    lines.append("## Failure Handling")
    for hint in failure_hints:
        lines.append(f"- {hint}")
    lines.append("")
    lines.append("## References")
    lines.append("- See `references/source_step_map.md` for provenance and source spans.")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_skill_markdown(metadata: SkillMetadata, steps: list[SelectedStep]) -> str:
    """Render deterministic `SKILL.md` content."""
    return _render_frontmatter(metadata) + "\n\n" + _render_skill_body(steps=steps)


def render_source_step_map(steps: list[SelectedStep]) -> str:
    """Render source provenance map for synthesized steps."""
    lines: list[str] = []
    lines.append("# Source Step Map")
    lines.append("")
    lines.append("This file records the extraction provenance used to build `SKILL.md`.")
    lines.append("")
    for index, step in enumerate(steps, start=1):
        lines.append(f"## Step {index}")
        lines.append(f"- source_item_id: `{step.source_item_id}`")
        lines.append(f"- source_id: `{step.source_id}`")
        lines.append(f"- confidence: `{step.confidence.value}`")
        lines.append(f"- tags: `{', '.join(step.tags) or 'untagged'}`")
        if step.span is None:
            lines.append("- span: `unmapped`")
        else:
            lines.append(
                "- span: "
                f"`{step.span.section_title}:{step.span.section_line_start}-{step.span.section_line_end}`"
            )
        if step.preconditions:
            lines.append("- preconditions:")
            for pre in step.preconditions:
                lines.append(f"  - {pre}")
        if step.postconditions:
            lines.append("- postconditions:")
            for post in step.postconditions:
                lines.append(f"  - {post}")
        lines.append(f"- text: {step.text}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def validate_skill_directory(skill_dir: Path) -> tuple[bool, str]:
    """Run `agentskills validate` and return (ok, combined_output)."""
    try:
        result = subprocess.run(
            ["agentskills", "validate", str(skill_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`agentskills` CLI is not available in PATH.") from exc

    combined_output = "\n".join(
        part for part in (result.stdout.strip(), result.stderr.strip()) if part
    ).strip()
    return result.returncode == 0, combined_output


def synthesize_skill_from_preview(
    preview_json: Path,
    output_root: Path = Path("skills/generated"),
    skill_name: str | None = None,
    validate: bool = True,
    max_steps: int = 24,
) -> SkillSynthesisResult:
    """Generate a skill package from phase-2 preview JSON."""
    payload = load_preview_payload(preview_json)
    generated_name = skill_name or suggest_skill_name(payload.benchmark_id)

    metadata = SkillMetadata(
        name=generated_name,
        description=_DEFAULT_DESCRIPTION,
        compatibility=_DEFAULT_COMPATIBILITY,
    )
    selected_steps = select_candidate_steps(payload, max_steps=max_steps)
    if not selected_steps:
        raise ValueError("no suitable steps selected from preview payload")

    skill_dir = (output_root / metadata.name).resolve()
    references_dir = skill_dir / "references"
    skill_md_path = skill_dir / "SKILL.md"
    reference_path = references_dir / "source_step_map.md"

    references_dir.mkdir(parents=True, exist_ok=True)
    skill_md_path.write_text(render_skill_markdown(metadata, selected_steps), encoding="utf-8")
    reference_path.write_text(render_source_step_map(selected_steps), encoding="utf-8")

    validation_ok = False
    if validate:
        validation_ok, output = validate_skill_directory(skill_dir)
        if not validation_ok:
            raise ValueError(f"generated skill failed validation:\n{output}")

    return SkillSynthesisResult(
        skill_dir=str(skill_dir),
        skill_md_path=str(skill_md_path),
        reference_path=str(reference_path),
        selected_step_count=len(selected_steps),
        validation_ran=validate,
        validation_ok=validation_ok if validate else False,
    )
