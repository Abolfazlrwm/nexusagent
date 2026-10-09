"""Provider for the Anthropic Messages API (with tool use)."""

from __future__ import annotations

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

DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


def _messages_to_wire(messages: Sequence[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """Return ``(system_prompt, messages)`` in Anthropic's format."""
    system_parts: list[str] = []
    wire: list[dict[str, Any]] = []

    for message in messages:
        call = message.tool_call
        if message.role == "system":
            system_parts.append(message.content)
        elif message.role == "assistant" and call is not None:
            block = {
                "type": "tool_use",
                "id": call.call_id or "call_0",
                "name": call.tool_name,
                "input": {TOOL_INPUT_KEY: call.tool_input},
            }
            wire.append({"role": "assistant", "content": [block]})
        elif message.role == "tool" and call is not None:
            block = {
                "type": "tool_result",
                "tool_use_id": call.call_id or "call_0",
                "content": message.content,
            }
            wire.append({"role": "user", "content": [block]})
        elif message.content.strip():  # the API rejects empty text content
            wire.append({"role": message.role, "content": message.content})

    return ("\n\n".join(system_parts) or None), wire


def _parse_response(payload: dict[str, Any]) -> ProviderResponse:
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        raise ProviderResponseError("response is missing 'content'")

    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue

        if block.get("type") == "tool_use":
            name = block.get("name")
            if not isinstance(name, str):
                raise ProviderResponseError("malformed tool_use block in response")
            call_id = block.get("id")
            return ToolCallRequest(
                tool_name=name,
                tool_input=extract_tool_input(block.get("input")),
                call_id=call_id if isinstance(call_id, str) else None,
            )

        if block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])

    text = "".join(texts)
    if not text.strip():
        raise ProviderResponseError("response contains no text content")

    return TextResponse(text)


class AnthropicProvider(Provider):
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
            raise ProviderConfigurationError("AnthropicProvider requires a configured model")

        if not self.config.api_key:
            raise ProviderConfigurationError("AnthropicProvider requires an API key")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("AnthropicProvider requires a positive timeout")

        system, wire_messages = _messages_to_wire(messages)
        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": wire_messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": tool_parameters_schema(t.description),
                }
                for t in tools
            ]

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": API_VERSION,
        }
        payload = post_json(
            self.config.endpoint or DEFAULT_ENDPOINT, body, headers, self.config.timeout
        )
        return _parse_response(payload)
