"""Contract tests for the async provider layer (ADR 0006)."""

from __future__ import annotations

import pytest

from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.provider import (
    AsyncProvider,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.providers import FakeProvider, ScriptedProvider

pytestmark = pytest.mark.asyncio


class TextOnlyAsyncProvider(AsyncProvider):
    async def generate(self, prompt: str) -> str:
        return f"async: {prompt}"


class BareTextProvider:
    """Not a Provider subclass at all: only ``generate()`` exists."""

    def generate(self, prompt: str) -> str:
        return f"bare: {prompt}"


async def test_sync_provider_adapter_generate() -> None:
    adapter = SyncProviderAdapter(FakeProvider())
    assert await adapter.generate("hi") == "fake response: hi"


async def test_async_provider_default_generate_response_wraps_generate() -> None:
    provider = TextOnlyAsyncProvider()
    assert await provider.generate_response("hi") == TextResponse("async: hi")


async def test_adapter_forwards_generate_response_arguments() -> None:
    scripted = ScriptedProvider([TextResponse("done")])
    adapter = SyncProviderAdapter(scripted)
    tools = (ToolSpec("upper", "Uppercase input."),)
    results = (ToolResult("upper", "hi", "HI"),)

    response = await adapter.generate_response("hello", tools=tools, tool_results=results)

    assert response == TextResponse("done")
    assert scripted.calls == [("hello", tools, results)]


async def test_adapter_returns_tool_call_requests() -> None:
    adapter = SyncProviderAdapter(ScriptedProvider([ToolCallRequest("upper", "hi")]))
    assert await adapter.generate_response("hello") == ToolCallRequest("upper", "hi")


async def test_adapter_surfaces_provider_exceptions() -> None:
    adapter = SyncProviderAdapter(ScriptedProvider([]))

    with pytest.raises(ProviderResponseError):
        await adapter.generate_response("hello")


async def test_adapter_falls_back_to_generate_without_generate_response() -> None:
    adapter = SyncProviderAdapter(BareTextProvider())
    assert await adapter.generate_response("hi") == TextResponse("bare: hi")
