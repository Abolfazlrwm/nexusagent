"""Generic HTTP Provider.

Wire format (see docs/protocol.md):

Request  ``POST <endpoint>`` with a JSON body::

    {"model": ..., "input": "<prompt>"}

  and, only when relevant, two extra keys::

    "tools":        [{"name": ..., "description": ...}, ...]
    "tool_results": [{"tool_name": ..., "tool_input": ..., "output": ...,
                      "is_error": false}, ...]

Response  a JSON object that is exactly one of::

    {"output": "<text answer>"}
    {"tool_name": "<tool>", "tool_input": "<input for the tool>"}

This module also hosts the shared streaming transport ``post_sse()``: the
HTTP-based providers request SSE streams (ADR 0009) through it, so header
handling, error mapping and timeout semantics stay defined in one place
next to ``post_json()``.
"""

from __future__ import annotations

import http.client
import json
import math
import random
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from typing import Any

from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

_BODY_SNIPPET_MAX_CHARS = 200
_SSE_DATA_FIELD = "data:"
_SSE_ACCEPT_VALUE = "text/event-stream"

# Retry policy (ADR 0011): transient request-level failures — connection
# errors, timeouts and these HTTP statuses — are retried with exponential
# backoff plus full jitter. Other statuses are permanent and fail fast.
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_BASE_DELAY_SECONDS = 0.5
_RETRY_MAX_DELAY_SECONDS = 8.0


def _retry_delay(attempt: int, headers: Any = None) -> float:
    """Return how long to wait before retry attempt ``attempt`` (0-based).

    An integer ``Retry-After`` hint wins when present (bounded by the max
    delay so the worst case stays predictable); otherwise the delay is
    exponential backoff (0.5s, 1s, 2s, 4s, ... capped at 8s) with full
    jitter, so concurrent clients do not retry in lockstep.
    """
    if headers is not None:
        raw = headers.get("Retry-After")
        if raw is not None:
            try:
                hint = float(raw)
            except ValueError:
                hint = -1.0  # HTTP-date form: out of scope, use backoff
            if math.isfinite(hint) and hint > 0:
                return min(hint, _RETRY_MAX_DELAY_SECONDS)

    cap = min(_RETRY_BASE_DELAY_SECONDS * (2**attempt), _RETRY_MAX_DELAY_SECONDS)
    return random.uniform(0.0, cap)


def _validate_retries(retries: int) -> None:
    if retries < 0:
        raise ProviderConfigurationError("Retries must not be negative")


def _open_response(
    request: urllib.request.Request,
    timeout: float,
    retries: int,
) -> Any:
    """Open ``request``, retrying transient failures up to ``retries`` times.

    The retry window covers the request itself — up to and including the
    response headers. Once the server starts answering (response body or SSE
    stream), nothing is retried: a retry could duplicate output the caller
    has already seen. This is the single place where retry policy, header
    handling and error mapping live (ADR 0011); the raised errors and their
    messages are identical to the pre-retry transport.
    """
    _validate_retries(retries)
    attempt = 0
    while True:
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRYABLE_STATUSES and attempt < retries:
                time.sleep(_retry_delay(attempt, exc.headers))
                attempt += 1
                continue
            # Include a short snippet of the response body when available:
            # real backends put useful context there (rate limits, auth).
            detail = _response_body_snippet(exc)
            raise ProviderRequestError(
                f"HTTP request failed with status {exc.code}{detail}"
            ) from None
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(_retry_delay(attempt))
                attempt += 1
                continue
            raise ProviderRequestError(f"HTTP request failed: {exc.reason}") from None
        except TimeoutError:
            if attempt < retries:
                time.sleep(_retry_delay(attempt))
                attempt += 1
                continue
            raise ProviderRequestError("HTTP request timed out") from None


def post_json(
    endpoint: str,
    body: dict[str, object],
    headers: dict[str, str],
    timeout: float,
    retries: int = 0,
) -> object:
    """POST ``body`` as JSON to ``endpoint`` and return the decoded response.

    This is the shared HTTP transport for the HTTP-based providers
    (``HttpProvider`` and ``OpenAIProvider``): it encodes the body, sends the
    request with the given headers, retries transient request-level failures
    ``retries`` times with exponential backoff (connection errors, timeouts,
    HTTP 429/5xx — never other statuses), maps HTTP/network failures to the
    typed provider errors (never leaking credentials), and decodes the JSON
    response. Callers own their configuration checks and wire formats.
    """
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    response = _open_response(request, timeout, retries)

    try:
        with response:
            raw = response.read()
    except TimeoutError:
        # A timeout while reading the body is not retried: the request was
        # already delivered, and a retry could produce duplicate side
        # effects on backends that are not inference-safe.
        raise ProviderRequestError("HTTP request timed out") from None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ProviderResponseError("HTTP response was not valid JSON") from None


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


def post_sse(
    endpoint: str,
    body: dict[str, object],
    headers: dict[str, str],
    timeout: float,
    retries: int = 0,
) -> Iterator[str]:
    """POST ``body`` as JSON to ``endpoint`` and stream back SSE data payloads.

    This is the shared streaming transport for the HTTP-based providers
    (ADR 0009): it encodes the body, sends the request with
    ``Accept: text/event-stream`` plus the given headers, and parses the
    response as a Server-Sent Events stream. It yields the raw data payload
    string of each event in arrival order; multi-line ``data:`` fields are
    joined with newlines, while event names, ids, retries and comment lines
    are ignored — the JSON payloads of the supported wire formats carry
    their own event types.

    Transient request-level failures are retried ``retries`` times with
    exponential backoff (ADR 0011) — but only until the response headers
    arrive. A mid-stream failure surfaces as ``ProviderRequestError``
    during iteration and is never retried: fragments the caller has
    already seen must not repeat. Callers own their configuration checks
    and wire formats.
    """
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Accept": _SSE_ACCEPT_VALUE, **headers},
        method="POST",
    )

    response = _open_response(request, timeout, retries)

    return _iter_sse_data(response)


def _iter_sse_data(response: Any) -> Iterator[str]:
    """Parse an open HTTP response as SSE and yield its ``data`` payloads."""
    data_lines: list[str] = []
    try:
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue  # SSE comment lines are keep-alives, not events

                if not line:
                    if data_lines:
                        yield "\n".join(data_lines)
                        data_lines = []
                    continue

                if line.startswith(_SSE_DATA_FIELD):
                    value = line[len(_SSE_DATA_FIELD) :]
                    if value.startswith(" "):
                        value = value[1:]
                    data_lines.append(value)
                # other SSE fields (event, id, retry) carry nothing we need

            if data_lines:  # flush a final event not terminated by a blank line
                yield "\n".join(data_lines)
    except (http.client.HTTPException, OSError, TimeoutError) as exc:
        raise ProviderRequestError(f"HTTP stream failed: {exc}") from None


class HttpProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        response = self.generate_response(prompt)

        if isinstance(response, ToolCallRequest):
            raise ProviderResponseError(
                "HTTP response requested a tool call; use generate_response() to handle it"
            )

        return response.text

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> ProviderResponse:
        """POST the stateless (prompt + tools + tool results) body to ``endpoint``.

        ``history`` is part of the 1.5 Provider contract (ADR 0014) and is
        accepted for signature compatibility; this provider has not opted
        into native history threading — the vendor-neutral protocol keeps
        carrying the composed transcript inside ``input`` (see
        ``docs/protocol.md``).
        """
        payload = self._post(self._build_body(prompt, tools, tool_results))
        return self._parse_payload(payload)

    def _build_body(
        self,
        prompt: str,
        tools: Sequence[ToolSpec],
        tool_results: Sequence[ToolResult],
    ) -> dict[str, object]:
        body: dict[str, object] = {"model": self.config.model, "input": prompt}

        if tools:
            body["tools"] = [{"name": t.name, "description": t.description} for t in tools]

        if tool_results:
            body["tool_results"] = [
                {
                    "tool_name": r.tool_name,
                    "tool_input": r.tool_input,
                    "output": r.output,
                    "is_error": r.is_error,
                }
                for r in tool_results
            ]

        return body

    def _post(self, body: dict[str, object]) -> object:
        if not self.config.endpoint:
            raise ProviderConfigurationError("HttpProvider requires a configured endpoint")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("HttpProvider requires a positive timeout")

        if self.config.retries < 0:
            raise ProviderConfigurationError("HttpProvider requires non-negative retries")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        return post_json(
            self.config.endpoint,
            body,
            headers,
            self.config.timeout,
            retries=self.config.retries,
        )

    @staticmethod
    def _parse_payload(payload: object) -> ProviderResponse:
        if not isinstance(payload, dict):
            raise ProviderResponseError("HTTP response must be a JSON object")

        has_output = "output" in payload
        has_tool_call = "tool_name" in payload

        if has_output and has_tool_call:
            raise ProviderResponseError(
                "HTTP response must contain either 'output' or 'tool_name', not both"
            )

        if has_tool_call:
            return HttpProvider._parse_tool_call(payload)

        if not has_output:
            raise ProviderResponseError("HTTP response is missing the 'output' field")

        output = payload["output"]
        if not isinstance(output, str):
            raise ProviderResponseError("HTTP response 'output' field must be a string")

        if not output.strip():
            raise ProviderResponseError("HTTP response 'output' field must not be empty")

        return TextResponse(output)

    @staticmethod
    def _parse_tool_call(payload: dict[str, object]) -> ToolCallRequest:
        tool_name = payload["tool_name"]
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ProviderResponseError(
                "HTTP response 'tool_name' field must be a non-empty string"
            )

        if "tool_input" not in payload:
            raise ProviderResponseError("HTTP response is missing the 'tool_input' field")

        tool_input = payload["tool_input"]
        if not isinstance(tool_input, str):
            raise ProviderResponseError("HTTP response 'tool_input' field must be a string")

        return ToolCallRequest(tool_name=tool_name, tool_input=tool_input)
