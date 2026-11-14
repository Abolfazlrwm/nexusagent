"""Provider for Gemini-compatible ``generateContent`` APIs.

Works with Google's Gemini API and with any server exposing the same wire
shape — gateways and proxies that speak the generateContent format — point
``ProviderConfig.endpoint`` at the server's **base URL**; the adapter appends
``/v1beta/models/{model}:generateContent`` (the model id is part of the URL
on this wire format). When no endpoint is configured, the official Gemini
API is used.

NexusAgent runs a stateless loop: every call receives the original prompt
plus the tool results accumulated so far. This provider rehydrates that
into the alternating-turn ``contents`` list the wire format expects: the
user prompt, then for each tool result a ``model`` turn carrying one
``functionCall`` part immediately followed by a ``user`` turn with the
matching ``functionResponse`` part. The call argument is synthesized as the
single ``input`` string, so no state needs to survive between iterations.

Because NexusAgent tools take and return a single string (ADR 0002), every
tool is declared with a Schema of one required string parameter named
``input`` (Gemini's OpenAPI-style subset spells the type enums uppercase:
``OBJECT``, ``STRING``). Models that pick their own single string parameter
name are accepted.

The generateContent format has no first-class error flag on
``functionResponse``, so tool results are fed back inside the required
response object: ``{"result": <output>}`` on success and ``{"error":
<message>}`` on failure — unlike the OpenAI adapter, the feedback stays
structured instead of relying on an ``Error: `` text prefix.

The prompt is always sent as the first ``user`` turn; the top-level
``systemInstruction`` parameter is not used, mirroring the OpenAI and
Anthropic adapters' decision to keep the stateless loop free of a hidden
system prompt (ADR 0008).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

from nexusagent.http_provider import post_json, post_sse
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderResponse,
    ProviderResponseError,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com"
_API_VERSION = "v1beta"
_GENERATE_ACTION = ":generateContent"
_STREAM_ACTION = ":streamGenerateContent"
_SSE_QUERY = "alt=sse"

_TOOL_INPUT_KEY = "input"
_RESULT_KEY = "result"
_ERROR_KEY = "error"


def _tool_input_schema() -> dict[str, Any]:
    """Schema for the arguments of one NexusAgent tool on the Gemini wire."""
    return {
        "type": "OBJECT",
        "properties": {
            _TOOL_INPUT_KEY: {
                "type": "STRING",
                "description": "Raw text input for the tool.",
            }
        },
        "required": [_TOOL_INPUT_KEY],
    }


def _tools_to_wire(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    """Map NexusAgent tool specs to Gemini function declarations."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": _tool_input_schema(),
        }
        for tool in tools
    ]


def _contents_for(prompt: str, tool_results: Sequence[ToolResult]) -> list[dict[str, Any]]:
    """Rehydrate the stateless (prompt + tool results) loop into contents turns."""
    contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]

    for result in tool_results:
        contents.append(
            {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "name": result.tool_name,
                            "args": {_TOOL_INPUT_KEY: result.tool_input},
                        }
                    }
                ],
            }
        )

        response_object: dict[str, Any] = {_RESULT_KEY: result.output}
        if result.is_error:
            response_object = {_ERROR_KEY: result.output}
        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": result.tool_name,
                            "response": response_object,
                        }
                    }
                ],
            }
        )

    return contents


def _request_url(endpoint: str | None, model: str, action: str = _GENERATE_ACTION) -> str:
    """Compose a generateContent-family URL from the endpoint base and model id."""
    base = (endpoint or DEFAULT_ENDPOINT).rstrip("/")
    return f"{base}/{_API_VERSION}/models/{model}{action}"


def _extract_tool_input(arguments: dict[str, Any]) -> str:
    """Pull the tool's string input out of a model-produced args object."""
    value = arguments.get(_TOOL_INPUT_KEY)
    if value is None and len(arguments) == 1:
        # Be lenient with models that pick their own parameter name.
        value = next(iter(arguments.values()))

    if not isinstance(value, str):
        raise ProviderResponseError(f"tool call input must contain a string {_TOOL_INPUT_KEY!r}")

    return value


def _parse_response(payload: object) -> ProviderResponse:
    if not isinstance(payload, dict):
        raise ProviderResponseError("Gemini response must be a JSON object")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ProviderResponseError("Gemini response is missing a non-empty 'candidates' list")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise ProviderResponseError("Gemini response candidates must be objects")

    content = candidate.get("content")
    if not isinstance(content, dict):
        raise ProviderResponseError("Gemini response candidate is missing a 'content' object")

    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ProviderResponseError("Gemini response content is missing a non-empty 'parts' list")

    for part in parts:
        if not isinstance(part, dict):
            raise ProviderResponseError("Gemini response content parts must be objects")

    function_call = _first_function_call(parts)
    if function_call is not None:
        return _parse_function_call(function_call)

    return _parse_text(parts)


def _first_function_call(parts: list[Any]) -> dict[str, Any] | None:
    """Return the first part carrying a ``functionCall``, or None when none.

    Only the first call is handled: the Agent feeds its result back and the
    model re-requests any further tools in the next iteration. This matches
    the single-request-per-iteration shape of the other adapters.
    """
    for part in parts:
        if isinstance(part, dict) and "functionCall" in part:
            return part

    return None


def _parse_function_call(part: dict[str, Any]) -> ToolCallRequest:
    call = part["functionCall"]
    if not isinstance(call, dict):
        raise ProviderResponseError("Gemini functionCall part must hold an object")

    tool_name = call.get("name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ProviderResponseError("Gemini functionCall must have a non-empty 'name'")

    arguments = call.get("args")
    if not isinstance(arguments, dict):
        raise ProviderResponseError("Gemini functionCall must have an 'args' object")

    return ToolCallRequest(tool_name=tool_name, tool_input=_extract_tool_input(arguments))


def _parse_text(parts: list[Any]) -> TextResponse:
    """Join the ``text`` parts of a response content list.

    Unknown content part types (future additions to the wire format) are
    skipped; a response with no usable text at all is an error.
    """
    collected: list[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            text = part["text"]
            if not isinstance(text, str):
                raise ProviderResponseError("Gemini text part must hold a string 'text'")
            collected.append(text)

    text = "".join(collected)
    if not text.strip():
        raise ProviderResponseError("Gemini response has no text content")

    return TextResponse(text)


class GeminiProvider(Provider):
    """A provider that talks to Gemini-compatible generateContent APIs.

    Configuration (``ProviderConfig``):

    - ``model`` is **required** — the model id is part of the request URL.
    - ``endpoint`` is optional; it is the **base URL** of the API and
      defaults to the official Gemini API. The adapter appends
      ``/v1beta/models/{model}:generateContent``, so the same adapter runs
      against any Gemini-compatible gateway.
    - ``api_key`` is optional — compatible gateways may not need one. When
      set, it is sent as the ``x-goog-api-key`` header (never as a query
      parameter, so it stays out of URLs and logs) and never appears in
      error messages or reprs. The official Gemini API requires it.
    - ``timeout`` must be positive (default 30 seconds).

    ``max_tokens`` caps the answer length through ``generationConfig``'s
    ``maxOutputTokens``. Unlike the Anthropic wire format it is optional on
    this wire: by default the adapter sends no ``generationConfig`` at all,
    and an explicit ``max_tokens`` must be a positive integer.
    """

    def __init__(
        self, config: ProviderConfig | None = None, *, max_tokens: int | None = None
    ) -> None:
        self.config = config or ProviderConfig()
        self.max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        response = self.generate_response(prompt)

        if isinstance(response, ToolCallRequest):
            raise ProviderResponseError(
                "Gemini response requested a tool call; use generate_response() to handle it"
            )

        return response.text

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        self._validate_config()

        body: dict[str, object] = {"contents": _contents_for(prompt, tool_results)}

        if tools:
            body["tools"] = _tools_to_wire(tools)

        if self.max_tokens is not None:
            body["generationConfig"] = {"maxOutputTokens": self.max_tokens}

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["x-goog-api-key"] = self.config.api_key

        # _validate_config() guarantees a non-empty model; narrow for the URL.
        assert self.config.model is not None
        endpoint = _request_url(self.config.endpoint, self.config.model)
        payload = post_json(endpoint, body, headers, self.config.timeout)
        return _parse_response(payload)

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> Iterator[ProviderStreamEvent]:
        """Stream the response for ``prompt`` over the SSE wire format.

        Requests ``:streamGenerateContent?alt=sse`` and yields
        ``StreamTextDelta`` events as text parts arrive, then one final
        ``ProviderResponse``: the first ``functionCall`` if one was
        streamed, otherwise the joined text. Configuration errors raise
        when the method is called; network and protocol errors surface
        while the returned iterator is consumed.
        """
        self._validate_config()
        return self._stream_events(prompt, tools, tool_results)

    def _stream_events(
        self,
        prompt: str,
        tools: Sequence[ToolSpec],
        tool_results: Sequence[ToolResult],
    ) -> Iterator[ProviderStreamEvent]:
        body: dict[str, object] = {"contents": _contents_for(prompt, tool_results)}

        if tools:
            body["tools"] = _tools_to_wire(tools)

        if self.max_tokens is not None:
            body["generationConfig"] = {"maxOutputTokens": self.max_tokens}

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["x-goog-api-key"] = self.config.api_key

        # _validate_config() guarantees a non-empty model; narrow for the URL.
        assert self.config.model is not None
        stream_path = _request_url(self.config.endpoint, self.config.model, _STREAM_ACTION)
        endpoint = f"{stream_path}?{_SSE_QUERY}"
        text_parts: list[str] = []
        tool_name: str | None = None
        tool_arguments: dict[str, Any] | None = None

        for data in post_sse(endpoint, body, headers, self.config.timeout):
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                raise ProviderResponseError("Gemini stream event was not valid JSON") from None

            if not isinstance(chunk, dict):
                raise ProviderResponseError("Gemini stream event must be a JSON object")

            if "error" in chunk:
                error = chunk["error"]
                message = error.get("message") if isinstance(error, dict) else None
                if not isinstance(message, str):
                    message = json.dumps(error)
                raise ProviderResponseError(f"Gemini stream error: {message}")

            candidates = chunk.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                continue  # usage-only and keep-alive chunks carry no content

            candidate = candidates[0]
            if not isinstance(candidate, dict):
                continue

            content = candidate.get("content")
            if not isinstance(content, dict):
                continue

            parts = content.get("parts")
            if not isinstance(parts, list):
                continue

            for part in parts:
                if not isinstance(part, dict):
                    continue

                if "text" in part:
                    text = part["text"]
                    if not isinstance(text, str):
                        raise ProviderResponseError("Gemini text part must hold a string 'text'")
                    text_parts.append(text)
                    yield StreamTextDelta(text)
                elif "functionCall" in part and tool_name is None:
                    # Only the first functionCall is consumed; later calls are
                    # re-requested by the model in the next loop iteration.
                    call = part["functionCall"]
                    if not isinstance(call, dict):
                        raise ProviderResponseError("Gemini functionCall part must hold an object")

                    name = call.get("name")
                    if not isinstance(name, str) or not name.strip():
                        raise ProviderResponseError(
                            "Gemini functionCall must have a non-empty 'name'"
                        )

                    arguments = call.get("args")
                    if not isinstance(arguments, dict):
                        raise ProviderResponseError(
                            "Gemini functionCall must have an 'args' object"
                        )

                    tool_name = name
                    tool_arguments = arguments

        if tool_name is not None and tool_arguments is not None:
            yield ToolCallRequest(
                tool_name=tool_name, tool_input=_extract_tool_input(tool_arguments)
            )
            return

        text = "".join(text_parts)
        if not text.strip():
            raise ProviderResponseError("Gemini stream ended without text or a tool call")

        yield TextResponse(text)

    def _validate_config(self) -> None:
        if not self.config.model or not self.config.model.strip():
            raise ProviderConfigurationError("GeminiProvider requires a configured model")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("GeminiProvider requires a positive timeout")

        if self.max_tokens is not None and not _is_positive_int(self.max_tokens):
            raise ProviderConfigurationError(
                "GeminiProvider requires a positive integer max_tokens"
            )


def _is_positive_int(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
