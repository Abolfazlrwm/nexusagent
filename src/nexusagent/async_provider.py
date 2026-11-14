"""Sync-to-async bridge for providers.

ADR 0006 keeps the core sync-first: the async layer is additive and the only
bridging mechanism is ``asyncio.to_thread``, which runs the blocking
``Provider`` calls in worker threads. This keeps the zero-runtime-dependency
promise (no HTTP client library) while letting every existing provider —
fake, scripted, http, openai — drive ``AsyncAgent`` unchanged.

For natively async backends, subclass ``AsyncProvider`` (defined next to the
sync contract in :mod:`nexusagent.provider`) directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import cast

from nexusagent.provider import (
    AsyncProvider,
    Provider,
    ProviderResponse,
    ProviderStreamEvent,
    TextResponse,
    ToolResult,
    ToolSpec,
)

__all__ = ["SyncProviderAdapter"]


class SyncProviderAdapter(AsyncProvider):
    """Expose any sync ``Provider`` as an ``AsyncProvider``.

    Blocking calls run in worker threads through ``asyncio.to_thread``, so
    the event loop never stalls. Tool-capable sync providers keep their
    ``generate_response()`` contract: the adapter forwards ``tools`` and
    ``tool_results`` unchanged and returns whatever the provider answered.
    """

    def __init__(self, provider: Provider) -> None:
        self._provider = provider

    async def generate(self, prompt: str) -> str:
        return await asyncio.to_thread(self._provider.generate, prompt)

    async def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        generate_response = getattr(self._provider, "generate_response", None)
        if generate_response is None:
            return TextResponse(await asyncio.to_thread(self._provider.generate, prompt))

        response: ProviderResponse = await asyncio.to_thread(
            generate_response, prompt, tools=tools, tool_results=tool_results
        )
        return response

    async def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Bridge the wrapped provider's stream into the event loop (ADR 0009).

        Streaming sync providers are consumed one event at a time in worker
        threads through ``asyncio.to_thread``, so the loop keeps yielding
        without stalling; providers without their own ``stream_response()``
        fall back to the complete ``generate_response()`` answer as a
        single event.
        """
        stream = getattr(self._provider, "stream_response", None)
        if stream is None:
            generate_response = getattr(self._provider, "generate_response", None)
            if generate_response is None:
                yield TextResponse(await asyncio.to_thread(self._provider.generate, prompt))
                return
            yield await asyncio.to_thread(
                generate_response, prompt, tools=tools, tool_results=tool_results
            )
            return

        iterator = stream(prompt, tools=tools, tool_results=tool_results)
        sentinel = object()
        while True:
            event = await asyncio.to_thread(next, iterator, sentinel)
            if event is sentinel:
                return
            yield cast("ProviderStreamEvent", event)
