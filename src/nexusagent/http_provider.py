"""Generic HTTP provider and the shared JSON-over-HTTP transport.

Wire format of the generic provider
-----------------------------------
``generate()`` POSTs ``{"model": ..., "input": <prompt>}`` and expects
``{"output": "<text>"}``.

``respond()`` (used by the agent loop) POSTs::

    {"model": ..., "input": <last user text>,
     "messages": [{"role": ..., "content": ..., "tool_name"?, "tool_input"?, "call_id"?}],
     "tools": [{"name": ..., "description": ...}]}

and accepts either a final answer ``{"output": "<text>"}`` or a tool call
``{"tool_name": "<name>", "tool_input": "<text>", "call_id"?: "<id>"}``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from nexusagent.provider import (
    Message,
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolSpec,
    last_user_text,
)


def post_json(
    url: str, body: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    """POST ``body`` as JSON and return the decoded JSON object.

    Error messages never include request headers, so API keys cannot leak.
    """
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ProviderRequestError(f"HTTP request failed with status {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ProviderRequestError(f"HTTP request failed: {exc.reason}") from None
    except TimeoutError:
        raise ProviderRequestError("HTTP request timed out") from None
    except OSError as exc:  # connection reset, remote disconnect, ...
        raise ProviderRequestError(f"HTTP request failed: {type(exc).__name__}") from None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ProviderResponseError("HTTP response was not valid JSON") from None

    if not isinstance(payload, dict):
        raise ProviderResponseError("HTTP response must be a JSON object")

    return payload


def _parse_output(payload: dict[str, Any]) -> str:
    if "output" not in payload:
        raise ProviderResponseError("HTTP response is missing the 'output' field")

    output = payload["output"]
    if not isinstance(output, str):
        raise ProviderResponseError("HTTP response 'output' field must be a string")

    if not output.strip():
        raise ProviderResponseError("HTTP response 'output' field must not be empty")

    return output


def _parse_tool_call(payload: dict[str, Any]) -> ToolCallRequest:
    name = payload["tool_name"]
    if not isinstance(name, str) or not name.strip():
        raise ProviderResponseError("HTTP response 'tool_name' must be a non-empty string")

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, str):
        raise ProviderResponseError("HTTP response 'tool_input' must be a string")

    call_id = payload.get("call_id")
    if call_id is not None and not isinstance(call_id, str):
        raise ProviderResponseError("HTTP response 'call_id' must be a string")

    return ToolCallRequest(tool_name=name, tool_input=tool_input, call_id=call_id)


def _message_to_wire(message: Message) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_call is not None:
        wire["tool_name"] = message.tool_call.tool_name
        wire["tool_input"] = message.tool_call.tool_input
        if message.tool_call.call_id is not None:
            wire["call_id"] = message.tool_call.call_id
    return wire


class HttpProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.config.endpoint:
            raise ProviderConfigurationError("HttpProvider requires a configured endpoint")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("HttpProvider requires a positive timeout")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        return post_json(self.config.endpoint, body, headers, self.config.timeout)

    def generate(self, prompt: str) -> str:
        payload = self._post({"model": self.config.model, "input": prompt})
        return _parse_output(payload)

    def respond(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> ProviderResponse:
        payload = self._post(
            {
                "model": self.config.model,
                "input": last_user_text(messages),
                "messages": [_message_to_wire(m) for m in messages],
                "tools": [{"name": t.name, "description": t.description} for t in tools],
            }
        )

        if "tool_name" in payload:
            return _parse_tool_call(payload)

        if "output" in payload:
            return TextResponse(_parse_output(payload))

        raise ProviderResponseError("HTTP response must contain 'output' or 'tool_name'")
