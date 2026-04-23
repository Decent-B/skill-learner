"""Curated vulnerability categories for web exploit skill generation.

Categories intentionally stay broad (20-30 classes) so generated skills
remain reusable across products and reports instead of overfitting to one
exploit variant.
"""

from __future__ import annotations

from dataclasses import dataclass

_CWE_REF_BASE = "https://cwe.mitre.org/data/definitions/{cwe_id}.html"


@dataclass(frozen=True)
class VulnerabilityCategory:
    """One broad vulnerability class used for skill bootstrapping and routing."""

    slug: str
    title: str
    summary: str
    cwe_ids: tuple[int, ...]
    trigger_hints: tuple[str, ...]

    @property
    def cwe_reference_urls(self) -> tuple[str, ...]:
        """Return official CWE reference URLs for the category."""
        return tuple(_CWE_REF_BASE.format(cwe_id=cwe_id) for cwe_id in self.cwe_ids)


GENERAL_OBSERVATION_SKILL_SLUG = "general_observation"
SKILL_AUTHORING_GUIDANCE_SLUG = "skill_authoring_guidance"

# Research basis:
# - CWE Top 25 2024:
#   https://cwe.mitre.org/top25/archive/2024/2024_top25_list.html
# - CWE simplified mapping slice:
#   https://cwe.mitre.org/data/slices/1003.html
WEB_VULNERABILITY_CATEGORIES: tuple[VulnerabilityCategory, ...] = (
    VulnerabilityCategory(
        slug="sql_injection",
        title="SQL Injection",
        summary="Inject untrusted input into SQL interpreters to alter query logic.",
        cwe_ids=(89,),
        trigger_hints=("sql", "database", "query", "injection", "union select"),
    ),
    VulnerabilityCategory(
        slug="cross_site_scripting",
        title="Cross-Site Scripting",
        summary="Execute attacker-controlled script in victim browser context.",
        cwe_ids=(79,),
        trigger_hints=("xss", "script", "html", "dom", "javascript"),
    ),
    VulnerabilityCategory(
        slug="command_injection",
        title="Command Injection",
        summary="Inject attacker-controlled input into shell/OS command execution paths.",
        cwe_ids=(78, 77),
        trigger_hints=("command", "shell", "exec", "os", "rce"),
    ),
    VulnerabilityCategory(
        slug="path_traversal",
        title="Path Traversal",
        summary="Escape restricted directories to read or write unintended files.",
        cwe_ids=(22,),
        trigger_hints=("path traversal", "../", "file read", "lfi", "rfi"),
    ),
    VulnerabilityCategory(
        slug="unrestricted_file_upload",
        title="Unrestricted File Upload",
        summary="Upload dangerous files that lead to code execution or data exposure.",
        cwe_ids=(434,),
        trigger_hints=("upload", "file type", "extension", "shell upload"),
    ),
    VulnerabilityCategory(
        slug="server_side_request_forgery",
        title="Server-Side Request Forgery",
        summary="Force server-side components to send attacker-directed network requests.",
        cwe_ids=(918,),
        trigger_hints=("ssrf", "internal request", "metadata service", "fetch url"),
    ),
    VulnerabilityCategory(
        slug="cross_site_request_forgery",
        title="Cross-Site Request Forgery",
        summary="Trigger state-changing actions with victim session context.",
        cwe_ids=(352,),
        trigger_hints=("csrf", "state change", "missing token", "forged request"),
    ),
    VulnerabilityCategory(
        slug="broken_authentication",
        title="Broken Authentication",
        summary="Bypass or weaken identity verification and session establishment.",
        cwe_ids=(287, 306),
        trigger_hints=("login bypass", "missing auth", "credential check", "session"),
    ),
    VulnerabilityCategory(
        slug="broken_authorization",
        title="Broken Authorization",
        summary="Access resources or actions outside allowed privilege boundaries.",
        cwe_ids=(862, 863, 269),
        trigger_hints=("idor", "access control", "privilege escalation", "unauthorized"),
    ),
    VulnerabilityCategory(
        slug="insecure_deserialization",
        title="Insecure Deserialization",
        summary="Deserialize untrusted data leading to gadget execution or logic abuse.",
        cwe_ids=(502,),
        trigger_hints=("deserialize", "serialized", "object injection", "gadget"),
    ),
    VulnerabilityCategory(
        slug="sensitive_data_exposure",
        title="Sensitive Data Exposure",
        summary="Expose secrets or sensitive information to unauthorized actors.",
        cwe_ids=(200,),
        trigger_hints=("leak", "disclosure", "secret", "credential", "token"),
    ),
    VulnerabilityCategory(
        slug="security_misconfiguration",
        title="Security Misconfiguration",
        summary="Unsafe defaults or deployment settings create exploitable conditions.",
        cwe_ids=(16,),
        trigger_hints=("misconfiguration", "default", "debug", "unsafe setting"),
    ),
    VulnerabilityCategory(
        slug="hardcoded_credentials",
        title="Hardcoded Credentials",
        summary="Embed static credentials in code, configs, or artifacts.",
        cwe_ids=(798,),
        trigger_hints=("hardcoded", "credential", "password", "private key"),
    ),
    VulnerabilityCategory(
        slug="weak_cryptography",
        title="Weak Cryptography",
        summary="Use broken or insufficient cryptographic algorithms and parameters.",
        cwe_ids=(327, 326),
        trigger_hints=("crypto", "cipher", "weak hash", "deprecated algorithm"),
    ),
    VulnerabilityCategory(
        slug="insecure_randomness",
        title="Insecure Randomness",
        summary="Use predictable random values in security-sensitive operations.",
        cwe_ids=(330,),
        trigger_hints=("random", "nonce", "token generation", "predictable"),
    ),
    VulnerabilityCategory(
        slug="open_redirect",
        title="Open Redirect",
        summary="Redirect users to attacker-controlled destinations.",
        cwe_ids=(601,),
        trigger_hints=("redirect", "next url", "return url", "location header"),
    ),
    VulnerabilityCategory(
        slug="xml_external_entity",
        title="XML External Entity",
        summary="Process untrusted XML entities that read files or pivot network calls.",
        cwe_ids=(611,),
        trigger_hints=("xxe", "xml parser", "entity", "doctype"),
    ),
    VulnerabilityCategory(
        slug="template_injection",
        title="Template Injection",
        summary="Inject expressions into server-side template rendering pipelines.",
        cwe_ids=(1336,),
        trigger_hints=("ssti", "template", "expression", "render"),
    ),
    VulnerabilityCategory(
        slug="clickjacking",
        title="Clickjacking",
        summary="Trick users into interacting with concealed UI layers/frames.",
        cwe_ids=(1021,),
        trigger_hints=("clickjacking", "frame", "ui redress", "x-frame-options"),
    ),
    VulnerabilityCategory(
        slug="http_request_smuggling",
        title="HTTP Request Smuggling",
        summary="Exploit parser disagreement across HTTP hops to desynchronize traffic.",
        cwe_ids=(444,),
        trigger_hints=("request smuggling", "te cl", "desync", "http parser"),
    ),
    VulnerabilityCategory(
        slug="header_injection",
        title="Header Injection",
        summary="Inject crafted header values to split responses or alter behavior.",
        cwe_ids=(113,),
        trigger_hints=("header injection", "response splitting", "crlf", "set-cookie"),
    ),
    VulnerabilityCategory(
        slug="insecure_file_permissions",
        title="Insecure File Permissions",
        summary="Misconfigured file permissions expose sensitive data or code paths.",
        cwe_ids=(732,),
        trigger_hints=("permissions", "world-readable", "config file", "access rights"),
    ),
    VulnerabilityCategory(
        slug="race_condition",
        title="Race Condition",
        summary="Exploit timing windows in state transitions and resource updates.",
        cwe_ids=(362,),
        trigger_hints=("race", "concurrent", "time of check", "time of use"),
    ),
    VulnerabilityCategory(
        slug="resource_exhaustion",
        title="Resource Exhaustion",
        summary="Consume CPU, memory, or I/O resources to degrade availability.",
        cwe_ids=(400,),
        trigger_hints=("dos", "resource exhaustion", "memory leak", "unbounded"),
    ),
)


def category_by_slug(slug: str) -> VulnerabilityCategory | None:
    """Return a category by slug, or None if unknown."""
    for category in WEB_VULNERABILITY_CATEGORIES:
        if category.slug == slug:
            return category
    return None


def category_slugs() -> tuple[str, ...]:
    """Return all category slugs in deterministic order."""
    return tuple(category.slug for category in WEB_VULNERABILITY_CATEGORIES)
