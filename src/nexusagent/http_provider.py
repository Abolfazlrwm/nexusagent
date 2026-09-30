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
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence

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
    ) -> ProviderResponse:
        payload = self._post(self._build_body(prompt, tools, tool_results))
        return self._parse_payload(payload)

    def _build_body(
        self,
        prompt: str,
        tools: Sequence[ToolSpec],
        tool_results: Sequence[ToolResult],
    ) -> dict:
        body: dict = {"model": self.config.model, "input": prompt}

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

    def _post(self, body: dict) -> object:
        if not self.config.endpoint:
            raise ProviderConfigurationError("HttpProvider requires a configured endpoint")

        if self.config.timeout <= 0:
            raise ProviderConfigurationError("HttpProvider requires a positive timeout")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ProviderRequestError(f"HTTP request failed with status {exc.code}") from None
        except urllib.error.URLError as exc:
            raise ProviderRequestError(f"HTTP request failed: {exc.reason}") from None
        except TimeoutError:
            raise ProviderRequestError("HTTP request timed out") from None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ProviderResponseError("HTTP response was not valid JSON") from None

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
    def _parse_tool_call(payload: dict) -> ToolCallRequest:
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
