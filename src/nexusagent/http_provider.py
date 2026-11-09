from __future__ import annotations

import json
import urllib.error
import urllib.request

from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)

_BODY_SNIPPET_MAX_CHARS = 200


def _response_body_snippet(exc: urllib.error.HTTPError) -> str:
    """Return a short, single-line snippet of an HTTP error body (best effort)."""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 — the body is optional context, never fatal
        return ""

    if not body:
        return ""

    snippet = " ".join(body.split())
    if len(snippet) > _BODY_SNIPPET_MAX_CHARS:
        snippet = snippet[:_BODY_SNIPPET_MAX_CHARS] + "..."
    return f": {snippet}"


class HttpProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        if not self.config.endpoint:
            raise ProviderConfigurationError("HttpProvider requires a configured endpoint")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("HttpProvider requires a positive timeout")

        body = json.dumps({"model": self.config.model, "input": prompt}).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib.request.Request(
            self.config.endpoint, data=body, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # Include a short snippet of the response body when available: real
            # backends put useful context there (rate limits, auth failures, ...).
            detail = _response_body_snippet(exc)
            raise ProviderRequestError(
                f"HTTP request failed with status {exc.code}{detail}"
            ) from None
        except urllib.error.URLError as exc:
            raise ProviderRequestError(f"HTTP request failed: {exc.reason}") from None
        except TimeoutError:
            raise ProviderRequestError("HTTP request timed out") from None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise ProviderResponseError("HTTP response was not valid JSON") from None

        if not isinstance(payload, dict):
            raise ProviderResponseError("HTTP response must be a JSON object")

        if "output" not in payload:
            raise ProviderResponseError("HTTP response is missing the 'output' field")

        output = payload["output"]
        if not isinstance(output, str):
            raise ProviderResponseError("HTTP response 'output' field must be a string")

        if not output.strip():
            raise ProviderResponseError("HTTP response 'output' field must not be empty")

        return output
