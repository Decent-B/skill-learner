"""HTTP client wrapper with retry semantics for source connectors."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
    return False


class HTTPClient:
    """Thin retrying HTTP client used by connectors."""

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        default_headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "User-Agent": "skill-learner-web-cybersecurity/0.1",
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        }
        if default_headers is not None:
            headers.update(default_headers)

        timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
            transport=transport,
        )

    def close(self) -> None:
        """Close underlying connection pool."""
        self._client.close()

    def __enter__(self) -> HTTPClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Issue a GET request and raise for non-2xx responses."""
        response = self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def post(
        self,
        url: str,
        *,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Issue a POST request and raise for non-2xx responses."""
        response = self._client.post(url, json=json, headers=headers)
        response.raise_for_status()
        return response

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET and decode JSON payload."""
        return self.get(url, params=params, headers=headers).json()

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """GET and return response text."""
        return self.get(url, params=params, headers=headers).text

    def post_json(
        self,
        url: str,
        *,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """POST with JSON body and decode JSON response."""
        return self.post(url, json=json, headers=headers).json()
