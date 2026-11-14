from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class ProviderConfig:
    model: str | None = None
    api_key: str | None = None
    endpoint: str | None = None
    timeout: float = 30.0

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"ProviderConfig(model={self.model!r}, api_key={api_key_display}, "
            f"endpoint={self.endpoint!r}, timeout={self.timeout!r})"
        )


@dataclass(frozen=True)
class TextResponse:
    """A plain text response from a Provider."""

    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """A request from a Provider to call a specific Tool."""

    tool_name: str
    tool_input: str


ProviderResponse = TextResponse | ToolCallRequest
"""What a Provider can answer with: either a plain text answer or a request
to call a tool. This is what ``Provider.generate_response()`` returns and what
the Agent's tool loop consumes."""


@dataclass(frozen=True)
class StreamTextDelta:
    """One incremental fragment of provider text, delivered as it is generated."""

    text: str


ProviderStreamEvent = StreamTextDelta | ProviderResponse
"""What ``Provider.stream_response()`` yields: zero or more
:class:`StreamTextDelta` fragments as text arrives, followed by exactly one
final ``ProviderResponse`` — the complete answer the tool loop consumes."""


@dataclass(frozen=True)
class ToolSpec:
    """A tool advertised to the Provider so it knows what it may request."""

    name: str
    description: str


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a ``ToolCallRequest``, fed back to the Provider.

    ``is_error`` is True when the tool could not be run or failed; ``output``
    then holds the error message so the model can recover or explain.
    """

    tool_name: str
    tool_input: str
    output: str
    is_error: bool = False


class Provider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        """Return a structured response for ``prompt``.

        ``tools`` lists the tools the Provider may request; ``tool_results``
        holds the results of tool calls it already requested in this run, in
        order. The default implementation wraps ``generate()`` and therefore
        only ever answers with text, so text-only Providers need no changes.
        Providers that can request tools override this method.
        """
        return TextResponse(self.generate(prompt))

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> Iterator[ProviderStreamEvent]:
        """Stream a structured response for ``prompt`` as it is generated.

        Yields zero or more :class:`StreamTextDelta` events as text arrives,
        then exactly one final ``ProviderResponse`` — the same object
        ``generate_response()`` returns, carrying the complete accumulated
        text. The default implementation does not stream: it requests the
        complete response and yields it as the only event, so text-only
        Providers need no changes. Providers backed by a streaming wire
        format override this method; configuration errors surface when the
        method is called, network and protocol errors while the returned
        iterator is consumed.
        """
        yield self.generate_response(prompt, tools=tools, tool_results=tool_results)


class AsyncProvider(ABC):
    """Async mirror of the sync ``Provider`` contract (ADR 0006).

    Same response protocol as ``Provider`` — ``generate()`` for plain text
    and ``generate_response()`` for the tool loop — but awaited. Implement
    this ABC for natively async backends; wrap any sync ``Provider`` with
    ``nexusagent.async_provider.SyncProviderAdapter`` to reuse it under
    ``AsyncAgent`` unchanged.
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...

    async def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        """Return a structured response for ``prompt``, awaited.

        The default implementation wraps ``generate()`` and therefore only
        ever answers with text, mirroring the sync ``Provider`` default.
        Async providers that can request tools override this method.
        """
        return TextResponse(await self.generate(prompt))

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Stream a structured response for ``prompt``, awaited (ADR 0009).

        Async mirror of the sync ``stream_response()`` contract: yields zero
        or more ``StreamTextDelta`` events, then exactly one final
        ``ProviderResponse``. The default implementation awaits the complete
        response and yields it as the only event; natively streaming async
        providers override this with an async iterator.
        """

        async def _stream() -> AsyncIterator[ProviderStreamEvent]:
            yield await self.generate_response(prompt, tools=tools, tool_results=tool_results)

        return _stream()


class ProviderError(Exception):
    """Base exception for provider-related failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider configuration is invalid for a provider."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request fails."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response is invalid."""
