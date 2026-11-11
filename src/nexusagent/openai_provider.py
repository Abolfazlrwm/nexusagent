"""Provider for OpenAI-compatible Chat Completions APIs.

Works with OpenAI itself and with any server exposing the same API shape:
Ollama (``http://localhost:11434/v1/chat/completions``), LM Studio, vLLM,
OpenRouter, Groq and others — point ``ProviderConfig.endpoint`` at the
``/v1/chat/completions`` route of your server. When no endpoint is
configured, the official OpenAI API is used.

NexusAgent runs a stateless loop: every call receives the original prompt
plus the tool results accumulated so far. This provider rehydrates that
into the multi-message conversation the OpenAI wire format expects: the
user prompt, then for each tool result a synthesized assistant message
carrying the tool call and a matching ``tool`` role message with the
result. Call ids are synthesized as ``call_0``, ``call_1``, ... so no
state needs to survive between iterations.

Because NexusAgent tools take and return a single string (ADR 0002), every
tool is advertised as a function with one required string parameter named
``input``. Models that pick their own single string parameter name are
accepted. Tool results that ended in an error are fed back with an
``Error: `` prefix so the model can tell a failed call from a successful
one and react.
"""

from __future__ import annotations

import json
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

DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"

_TOOL_INPUT_KEY = "input"
_ERROR_RESULT_PREFIX = "Error: "


def _tool_parameters_schema() -> dict[str, Any]:
    """JSON Schema for the arguments of one NexusAgent tool on the OpenAI wire."""
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
    """Map NexusAgent tool specs to OpenAI function-calling tool definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": _tool_parameters_schema(),
            },
        }
        for tool in tools
    ]


def _messages_for(prompt: str, tool_results: Sequence[ToolResult]) -> list[dict[str, Any]]:
    """Rehydrate the stateless (prompt + tool results) loop into OpenAI messages."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for index, result in enumerate(tool_results):
        call_id = f"call_{index}"
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": result.tool_name,
                            "arguments": json.dumps({_TOOL_INPUT_KEY: result.tool_input}),
                        },
                    }
                ],
            }
        )
        content = result.output
        if result.is_error:
            content = f"{_ERROR_RESULT_PREFIX}{content}"
        messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    return messages


def _extract_tool_input(arguments: object) -> str:
    """Pull the tool's string input out of a model-produced arguments object."""
    if not isinstance(arguments, dict):
        raise ProviderResponseError("tool call arguments must be a JSON object")

    value = arguments.get(_TOOL_INPUT_KEY)
    if value is None and len(arguments) == 1:
        # Be lenient with models that pick their own parameter name.
        value = next(iter(arguments.values()))

    if not isinstance(value, str):
        raise ProviderResponseError(
            f"tool call arguments must contain a string {_TOOL_INPUT_KEY!r}"
        )

    return value


def _parse_response(payload: object) -> ProviderResponse:
    if not isinstance(payload, dict):
        raise ProviderResponseError("OpenAI response must be a JSON object")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("OpenAI response is missing a non-empty 'choices' list")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ProviderResponseError("OpenAI response choice must be an object")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("OpenAI response choice is missing 'message'")

    tool_calls = message.get("tool_calls")
    if tool_calls:
        return _parse_tool_calls(tool_calls)

    return _parse_text(message)


def _parse_tool_calls(tool_calls: object) -> ToolCallRequest:
    """Parse the first tool call of a response.

    Only the first call is handled: the Agent feeds its result back and the
    model re-requests any further tools in the next iteration. This matches
    the single-request-per-iteration shape of the core tool loop.
    """
    if not isinstance(tool_calls, list) or not tool_calls:
        raise ProviderResponseError("OpenAI response 'tool_calls' must be a non-empty list")

    first_call = tool_calls[0]
    if not isinstance(first_call, dict):
        raise ProviderResponseError("OpenAI response tool call must be an object")

    function = first_call.get("function")
    if not isinstance(function, dict):
        raise ProviderResponseError("OpenAI response tool call is missing 'function'")

    tool_name = function.get("name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ProviderResponseError("OpenAI response tool call must have a non-empty 'name'")

    arguments: object = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            raise ProviderResponseError("tool call arguments were not valid JSON") from None

    return ToolCallRequest(tool_name=tool_name, tool_input=_extract_tool_input(arguments))


def _parse_text(message: dict[str, Any]) -> TextResponse:
    content = message.get("content")
    if not isinstance(content, str):
        raise ProviderResponseError("OpenAI response message 'content' must be a string")

    if not content.strip():
        raise ProviderResponseError("OpenAI response message 'content' must not be empty")

    return TextResponse(content)


class OpenAIProvider(Provider):
    """A provider that talks to OpenAI-compatible Chat Completions APIs.

    Configuration (``ProviderConfig``):

    - ``model`` is **required** — Chat Completions always needs a model id.
    - ``endpoint`` is optional; it defaults to the official OpenAI API. Point
      it at Ollama, LM Studio, vLLM, OpenRouter, Groq, ... to run the same
      adapter against those servers.
    - ``api_key`` is optional — local servers such as Ollama do not need one.
      When set, it is sent as ``Authorization: Bearer <api_key>`` and never
      appears in error messages or reprs.
    - ``timeout`` must be positive (default 30 seconds).
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        response = self.generate_response(prompt)

        if isinstance(response, ToolCallRequest):
            raise ProviderResponseError(
                "OpenAI response requested a tool call; use generate_response() to handle it"
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
            "messages": _messages_for(prompt, tool_results),
        }

        if tools:
            body["tools"] = _tools_to_wire(tools)

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        endpoint = self.config.endpoint or DEFAULT_ENDPOINT
        payload = post_json(endpoint, body, headers, self.config.timeout)
        return _parse_response(payload)

    def _validate_config(self) -> None:
        if not self.config.model or not self.config.model.strip():
            raise ProviderConfigurationError("OpenAIProvider requires a configured model")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("OpenAIProvider requires a positive timeout")
