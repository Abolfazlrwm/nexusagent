"""Provider for OpenAI-compatible Chat Completions APIs.

Works with OpenAI itself and with any server exposing the same API: Ollama
(``http://localhost:11434/v1/chat/completions``), LM Studio, vLLM, OpenRouter,
Groq, and others. Tool calling uses the ``tools`` / ``tool_calls`` fields.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from nexusagent.http_provider import post_json
from nexusagent.provider import (
    Message,
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolSpec,
)
from nexusagent.wire import TOOL_INPUT_KEY, extract_tool_input, tool_parameters_schema

DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"


def _messages_to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for message in messages:
        call = message.tool_call
        if message.role == "assistant" and call is not None:
            wire.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.call_id or "call_0",
                            "type": "function",
                            "function": {
                                "name": call.tool_name,
                                "arguments": json.dumps({TOOL_INPUT_KEY: call.tool_input}),
                            },
                        }
                    ],
                }
            )
        elif message.role == "tool" and call is not None:
            wire.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id or "call_0",
                    "content": message.content,
                }
            )
        else:
            wire.append({"role": message.role, "content": message.content})
    return wire


def _tools_to_wire(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool_parameters_schema(tool.description),
            },
        }
        for tool in tools
    ]


def _parse_response(payload: dict[str, Any]) -> ProviderResponse:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderResponseError("response is missing 'choices'")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("response choice is missing 'message'")

    tool_calls = message.get("tool_calls")
    if tool_calls:
        # Only the first call is handled; the model re-requests any others
        # after seeing the first result.
        first = tool_calls[0] if isinstance(tool_calls, list) else None
        if not isinstance(first, dict):
            raise ProviderResponseError("malformed tool call in response")

        function = first.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise ProviderResponseError("malformed tool call in response")

        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise ProviderResponseError("tool call arguments were not valid JSON") from None

        call_id = first.get("id")
        return ToolCallRequest(
            tool_name=function["name"],
            tool_input=extract_tool_input(arguments),
            call_id=call_id if isinstance(call_id, str) else None,
        )

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("response contains no text content")

    return TextResponse(content)


class OpenAIProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        response = self.respond([Message("user", prompt)])
        if not isinstance(response, TextResponse):
            raise ProviderResponseError("unexpected tool call in response")
        return response.text

    def respond(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> ProviderResponse:
        if not self.config.model:
            raise ProviderConfigurationError("OpenAIProvider requires a configured model")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("OpenAIProvider requires a positive timeout")

        body: dict[str, Any] = {"model": self.config.model, "messages": _messages_to_wire(messages)}
        if tools:
            body["tools"] = _tools_to_wire(tools)

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = post_json(
            self.config.endpoint or DEFAULT_ENDPOINT, body, headers, self.config.timeout
        )
        return _parse_response(payload)
