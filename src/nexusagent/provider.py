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
    retries: int = 2

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"ProviderConfig(model={self.model!r}, api_key={api_key_display}, "
            f"endpoint={self.endpoint!r}, timeout={self.timeout!r}, "
            f"retries={self.retries!r})"
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
    """Sync provider contract.

    Class attributes:

    - ``supports_native_history`` — opt-in capability flag (ADR 0014).
      When False (the default for every user-written provider), the Agent
      composes remembered conversation turns into a single text prompt and
      passes no ``history`` argument at all, so the call shape a provider
      sees is exactly the pre-1.5 one. When True, the Agent instead passes
      the raw user input as ``prompt`` plus the remembered turns as the
      ``history`` keyword, and the provider rehydrates them into its native
      multi-message wire format. Built-in vendor adapters set the flag;
      subclasses that override ``generate_response()`` /
      ``stream_response()`` must accept the ``history`` keyword when they
      keep the flag set.
    """

    supports_native_history = False

    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> ProviderResponse:
        """Return a structured response for ``prompt``.

        ``tools`` lists the tools the Provider may request; ``tool_results``
        holds the results of tool calls it already requested in this run, in
        order. ``history`` carries remembered conversation turns as plain
        ``(role, text)`` pairs — role ``"user"`` or ``"assistant"``, oldest
        first (ADR 0014); it is non-empty only for providers that opted in
        via ``supports_native_history``, and every iteration of a run
        receives the same turns. The default implementation wraps
        ``generate()`` and therefore only ever answers with text, so
        text-only Providers need no changes. Providers that can request
        tools override this method.
        """
        return TextResponse(self.generate(prompt))

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> Iterator[ProviderStreamEvent]:
        """Stream a structured response for ``prompt`` as it is generated.

        Yields zero or more :class:`StreamTextDelta` events as text arrives,
        then exactly one final ``ProviderResponse`` — the same object
        ``generate_response()`` returns, carrying the complete accumulated
        text. ``history`` mirrors the :meth:`generate_response` contract
        (ADR 0014): non-empty turns are forwarded through to
        ``generate_response()``; an empty ``history`` keeps the exact
        pre-1.5 call shape. The default implementation does not stream: it
        requests the complete response and yields it as the only event, so
        text-only Providers need no changes. Providers backed by a
        streaming wire format override this method; configuration errors
        surface when the method is called, network and protocol errors
        while the returned iterator is consumed.
        """
        if history:
            yield self.generate_response(
                prompt, tools=tools, tool_results=tool_results, history=history
            )
        else:
            yield self.generate_response(prompt, tools=tools, tool_results=tool_results)


class AsyncProvider(ABC):
    """Async mirror of the sync ``Provider`` contract (ADR 0006).

    Same response protocol as ``Provider`` — ``generate()`` for plain text
    and ``generate_response()`` for the tool loop — but awaited. Implement
    this ABC for natively async backends; wrap any sync ``Provider`` with
    ``nexusagent.async_provider.SyncProviderAdapter`` to reuse it under
    ``AsyncAgent`` unchanged.

    Like the sync contract, ``supports_native_history`` (ADR 0014) opts an
    implementation into receiving remembered conversation turns as the
    ``history`` keyword instead of a composed text prompt; the default is
    False, so existing async providers keep the exact pre-1.5 call shape.
    """

    supports_native_history = False

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...

    async def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> ProviderResponse:
        """Return a structured response for ``prompt``, awaited.

        ``history`` mirrors the sync :meth:`Provider.generate_response`
        contract (ADR 0014). The default implementation wraps ``generate()``
        and therefore only ever answers with text, mirroring the sync
        ``Provider`` default. Async providers that can request tools
        override this method.
        """
        return TextResponse(await self.generate(prompt))

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Stream a structured response for ``prompt``, awaited (ADR 0009).

        Async mirror of the sync ``stream_response()`` contract: yields zero
        or more ``StreamTextDelta`` events, then exactly one final
        ``ProviderResponse``. ``history`` mirrors the sync contract
        (ADR 0014): non-empty turns are forwarded through to
        ``generate_response()``; an empty ``history`` keeps the exact
        pre-1.5 call shape. The default implementation awaits the complete
        response and yields it as the only event; natively streaming async
        providers override this with an async iterator.
        """

        async def _stream() -> AsyncIterator[ProviderStreamEvent]:
            if history:
                yield await self.generate_response(
                    prompt, tools=tools, tool_results=tool_results, history=history
                )
            else:
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
