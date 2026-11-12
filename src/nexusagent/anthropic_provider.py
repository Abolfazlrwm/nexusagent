"""Provider for Anthropic-compatible Messages APIs.

Works with Anthropic itself and with any server exposing the same API
shape — gateways and proxies that speak the Messages wire format — point
``ProviderConfig.endpoint`` at the ``/v1/messages`` route of your server.
When no endpoint is configured, the official Anthropic API is used.

NexusAgent runs a stateless loop: every call receives the original prompt
plus the tool results accumulated so far. This provider rehydrates that
into the alternating-turn conversation the Messages wire format expects:
the user prompt, then for each tool result an assistant message carrying
one ``tool_use`` block immediately followed by a user message with the
matching ``tool_result`` block. Call ids are synthesized as ``call_0``,
``call_1``, ... and only have to match inside this one request, so no
state needs to survive between iterations.

Because NexusAgent tools take and return a single string (ADR 0002), every
tool is advertised with a JSON Schema of one required string parameter
named ``input``. Models that pick their own single string parameter name
are accepted. Tool results that ended in an error are fed back with the
native ``is_error: true`` flag of the ``tool_result`` block — the Messages
wire format has a first-class error channel, so unlike the OpenAI adapter
no ``Error: `` prefix is needed.

The prompt is always sent as the first ``user`` message; the top-level
``system`` parameter is not used, mirroring the OpenAI adapter's decision
to keep the stateless loop free of a hidden system prompt (ADR 0007).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from nexusagent.http_provider import post_json
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
DEFAULT_MAX_TOKENS = 1024
_ANTHROPIC_VERSION = "2023-06-01"

_TOOL_INPUT_KEY = "input"


def _tool_input_schema() -> dict[str, Any]:
    """JSON Schema for the arguments of one NexusAgent tool on the Anthropic wire."""
    return {
        "type": "object",
        "properties": {
            _TOOL_INPUT_KEY: {
                "type": "string",
                "description": "Raw text input for the tool.",
            }
        },
        "required": [_TOOL_INPUT_KEY],
    }


def _tools_to_wire(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    """Map NexusAgent tool specs to Anthropic tool definitions."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": _tool_input_schema(),
        }
        for tool in tools
    ]


def _messages_for(prompt: str, tool_results: Sequence[ToolResult]) -> list[dict[str, Any]]:
    """Rehydrate the stateless (prompt + tool results) loop into Messages turns."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for index, result in enumerate(tool_results):
        call_id = f"call_{index}"
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": result.tool_name,
                        "input": {_TOOL_INPUT_KEY: result.tool_input},
                    }
                ],
            }
        )

        tool_result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": result.output,
        }
        if result.is_error:
            tool_result["is_error"] = True
        messages.append({"role": "user", "content": [tool_result]})

    return messages


def _extract_tool_input(arguments: dict[str, Any]) -> str:
    """Pull the tool's string input out of a model-produced input object."""
    value = arguments.get(_TOOL_INPUT_KEY)
    if value is None and len(arguments) == 1:
        # Be lenient with models that pick their own parameter name.
        value = next(iter(arguments.values()))

    if not isinstance(value, str):
        raise ProviderResponseError(f"tool call input must contain a string {_TOOL_INPUT_KEY!r}")

    return value


def _parse_response(payload: object) -> ProviderResponse:
    if not isinstance(payload, dict):
        raise ProviderResponseError("Anthropic response must be a JSON object")

    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise ProviderResponseError("Anthropic response is missing a non-empty 'content' list")

    for block in content:
        if not isinstance(block, dict):
            raise ProviderResponseError("Anthropic response content blocks must be objects")

    tool_use = _first_tool_use(content)
    if tool_use is not None:
        return _parse_tool_use(tool_use)

    return _parse_text(content)


def _first_tool_use(content: list[Any]) -> dict[str, Any] | None:
    """Return the first ``tool_use`` block, or None when there is none.

    Only the first call is handled: the Agent feeds its result back and the
    model re-requests any further tools in the next iteration. This matches
    the single-request-per-iteration shape of the core tool loop.
    """
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            return block

    return None


def _parse_tool_use(block: dict[str, Any]) -> ToolCallRequest:
    tool_name = block.get("name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ProviderResponseError("Anthropic tool_use block must have a non-empty 'name'")

    arguments = block.get("input")
    if not isinstance(arguments, dict):
        raise ProviderResponseError("Anthropic tool_use block must have an 'input' object")

    return ToolCallRequest(tool_name=tool_name, tool_input=_extract_tool_input(arguments))


def _parse_text(content: list[Any]) -> TextResponse:
    """Join the ``text`` blocks of a response content list.

    Unknown content block types (future additions to the wire format) are
    skipped; a response with no usable text at all is an error.
    """
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise ProviderResponseError("Anthropic text block must have a string 'text'")
            parts.append(text)

    text = "".join(parts)
    if not text.strip():
        raise ProviderResponseError("Anthropic response has no text content")

    return TextResponse(text)


class AnthropicProvider(Provider):
    """A provider that talks to Anthropic-compatible Messages APIs.

    Configuration (``ProviderConfig``):

    - ``model`` is **required** — every Messages request carries a model id.
    - ``endpoint`` is optional; it defaults to the official Anthropic API.
      Point it at any Anthropic-compatible gateway to run the same adapter
      against that server.
    - ``api_key`` is optional — compatible gateways may not need one. When
      set, it is sent as the ``x-api-key`` header and never appears in error
      messages or reprs. The official Anthropic API requires it.
    - ``timeout`` must be positive (default 30 seconds).

    ``max_tokens`` is the one extra knob the Messages wire format requires
    on every request; it defaults to ``DEFAULT_MAX_TOKENS`` and must be a
    positive integer when set explicitly.
    """

    def __init__(
        self, config: ProviderConfig | None = None, *, max_tokens: int | None = None
    ) -> None:
        self.config = config or ProviderConfig()
        self.max_tokens = DEFAULT_MAX_TOKENS if max_tokens is None else max_tokens

    def generate(self, prompt: str) -> str:
        response = self.generate_response(prompt)

        if isinstance(response, ToolCallRequest):
            raise ProviderResponseError(
                "Anthropic response requested a tool call; use generate_response() to handle it"
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

        body: dict[str, object] = {
            "model": self.config.model,
            "max_tokens": self.max_tokens,
            "messages": _messages_for(prompt, tool_results),
        }

        if tools:
            body["tools"] = _tools_to_wire(tools)

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }
        if self.config.api_key:
            headers["x-api-key"] = self.config.api_key

        endpoint = self.config.endpoint or DEFAULT_ENDPOINT
        payload = post_json(endpoint, body, headers, self.config.timeout)
        return _parse_response(payload)

    def _validate_config(self) -> None:
        if not self.config.model or not self.config.model.strip():
            raise ProviderConfigurationError("AnthropicProvider requires a configured model")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("AnthropicProvider requires a positive timeout")

        valid_max_tokens = (
            isinstance(self.max_tokens, int)
            and not isinstance(self.max_tokens, bool)
            and self.max_tokens > 0
        )
        if not valid_max_tokens:
            raise ProviderConfigurationError(
                "AnthropicProvider requires a positive integer max_tokens"
            )
