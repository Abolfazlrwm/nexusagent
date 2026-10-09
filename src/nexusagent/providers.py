from __future__ import annotations

from collections.abc import Iterable, Sequence

from nexusagent.provider import (
    Message,
    Provider,
    ProviderConfig,
    ProviderResponse,
    ProviderResponseError,
    TextResponse,
    ToolSpec,
)


class FakeProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        return f"fake response: {prompt}"


class ScriptedProvider(Provider):
    """Replays a fixed sequence of responses, one per call.

    Useful for tests and offline demos of the agent loop. Plain strings are
    treated as ``TextResponse``. Every call is recorded in ``calls`` as a
    ``(messages, tools)`` pair.
    """

    def __init__(self, responses: Iterable[ProviderResponse | str]) -> None:
        self._responses = [TextResponse(r) if isinstance(r, str) else r for r in responses]
        self._index = 0
        self.calls: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    def respond(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> ProviderResponse:
        self.calls.append((tuple(messages), tuple(tools)))
        if self._index >= len(self._responses):
            raise ProviderResponseError("ScriptedProvider has no more responses")
        response = self._responses[self._index]
        self._index += 1
        return response

    def generate(self, prompt: str) -> str:
        response = self.respond([Message("user", prompt)])
        if not isinstance(response, TextResponse):
            raise ProviderResponseError("ScriptedProvider.generate() needs a text response")
        return response.text
