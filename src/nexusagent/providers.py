from __future__ import annotations

from collections.abc import Iterable, Sequence

from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolResult,
    ToolSpec,
)


class FakeProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        return f"fake response: {prompt}"


class ScriptedProvider(Provider):
    """A deterministic, network-free Provider that replays a fixed script.

    Each call to ``generate_response()`` returns the next scripted
    ``ProviderResponse``. It is meant for demos and tests of the tool loop:
    script a ``ToolCallRequest`` followed by a ``TextResponse`` and the Agent
    will run the tool and finish. Every call is recorded in ``calls``.
    """

    def __init__(self, responses: Iterable[ProviderResponse]) -> None:
        self._responses = list(responses)
        self._position = 0
        self.calls: list[tuple[str, tuple[ToolSpec, ...], tuple[ToolResult, ...]]] = []

    def generate(self, prompt: str) -> str:
        response = self.generate_response(prompt)
        if not isinstance(response, TextResponse):
            raise ProviderResponseError("scripted response is a tool call, not text")
        return response.text

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        self.calls.append((prompt, tuple(tools), tuple(tool_results)))

        if self._position >= len(self._responses):
            raise ProviderResponseError("ScriptedProvider has no more scripted responses")

        response = self._responses[self._position]
        self._position += 1
        return response
