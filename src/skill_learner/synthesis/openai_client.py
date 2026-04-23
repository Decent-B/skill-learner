"""Thin OpenAI Chat Completions client with token usage extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import TokenUsageSnapshot


class OpenAIChatError(RuntimeError):
    """Raised when an OpenAI API call fails."""


@dataclass(frozen=True)
class OpenAIChatResponse:
    """Parsed OpenAI API response payload for one chat completion request."""

    text: str
    usage: TokenUsageSnapshot
    raw_response: dict[str, Any]


class OpenAIChatClient:
    """Minimal wrapper around `/v1/chat/completions` with retries."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        timeout_seconds: float = 120.0,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            base_url=base_url.rstrip("/"),
        )

    def close(self) -> None:
        """Close underlying HTTP client resources."""
        self._client.close()

    @property
    def model(self) -> str:
        """Return configured model name."""
        return self._model

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, OpenAIChatError)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def create_completion(
        self,
        *,
        messages: list[dict[str, str]],
        require_json_object: bool = False,
    ) -> OpenAIChatResponse:
        """Call OpenAI Chat Completions and return parsed text + usage."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if require_json_object:
            payload["response_format"] = {"type": "json_object"}

        response = self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            raise OpenAIChatError(
                f"OpenAI request failed ({response.status_code}): {response.text[:1200]}"
            )
        data = response.json()

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenAIChatError("OpenAI response missing choices.")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise OpenAIChatError("OpenAI response choice has invalid format.")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise OpenAIChatError("OpenAI response missing message object.")

        content = message.get("content")
        if not isinstance(content, str):
            raise OpenAIChatError("OpenAI response message content is not text.")

        usage = _parse_usage(data.get("usage"))
        return OpenAIChatResponse(text=content, usage=usage, raw_response=data)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, with fallback extraction."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise OpenAIChatError("Model output does not contain a JSON object.")

    candidate = text[start : end + 1]
    try:
        parsed_candidate = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise OpenAIChatError(f"Failed to parse model JSON output: {exc}") from exc
    if not isinstance(parsed_candidate, dict):
        raise OpenAIChatError("Parsed model output is not a JSON object.")
    return parsed_candidate


def _parse_usage(raw_usage: object) -> TokenUsageSnapshot:
    """Extract token accounting fields from OpenAI usage payload."""
    if not isinstance(raw_usage, dict):
        return TokenUsageSnapshot()

    prompt_tokens = _to_non_negative_int(raw_usage.get("prompt_tokens"))
    completion_tokens = _to_non_negative_int(raw_usage.get("completion_tokens"))
    total_tokens = _to_non_negative_int(raw_usage.get("total_tokens"))

    cached_tokens = 0
    prompt_details = raw_usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        cached_tokens = _to_non_negative_int(prompt_details.get("cached_tokens"))

    reasoning_tokens = 0
    completion_details = raw_usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning_tokens = _to_non_negative_int(completion_details.get("reasoning_tokens"))

    return TokenUsageSnapshot(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _to_non_negative_int(value: object) -> int:
    """Convert arbitrary value to non-negative integer fallbacking to zero."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            return max(0, int(stripped))
        except ValueError:
            return 0
    if value is None:
        return 0
    try:
        converted = int(str(value))
    except (TypeError, ValueError):
        return 0
    return max(0, converted)
