"""Contract tests for the async streaming layer (ADR 0009 over ADR 0006)."""

from collections.abc import Iterator

import pytest

from nexusagent.async_agent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_runtime import AsyncRuntime
from nexusagent.echo_tool import EchoTool
from nexusagent.provider import (
    AsyncProvider,
    Provider,
    ProviderResponseError,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolSpec,
)
from nexusagent.providers import ScriptedProvider
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry

pytestmark = pytest.mark.asyncio


class StreamingSyncProvider(Provider):
    """A sync provider with a real streaming ``stream_response()``."""

    def __init__(self) -> None:
        self.stream_calls = 0

    def generate(self, prompt: str) -> str:
        return f"plain: {prompt}"

    def stream_response(self, prompt, *, tools=(), tool_results=()):
        self.stream_calls += 1
        yield StreamTextDelta("Hel")
        yield StreamTextDelta("lo")
        yield TextResponse("Hello")


class StreamingAsyncProvider(AsyncProvider):
    """A natively async provider with a real async streaming contract."""

    def __init__(self, scripts: list[list[ProviderStreamEvent]]) -> None:
        self._scripts = scripts
        self._position = 0

    async def generate(self, prompt: str) -> str:
        raise AssertionError("generate() must not be called in these tests")

    async def stream_response(self, prompt, *, tools=(), tool_results=()):
        script = self._scripts[self._position]
        self._position += 1
        for event in script:
            yield event


class AsyncStreamlessProvider(AsyncProvider):
    """An async provider whose stream_response() must never be consumed."""

    def __init__(self) -> None:
        self.generate_response_calls = 0

    async def generate(self, prompt: str) -> str:
        return f"plain: {prompt}"

    async def generate_response(self, prompt, *, tools=(), tool_results=()):
        self.generate_response_calls += 1
        return TextResponse(f"plain: {prompt}")

    async def stream_response(self, prompt, *, tools=(), tool_results=()):
        raise AssertionError("stream_response must not be used without on_delta")
        yield  # pragma: no cover — makes this an async generator


def make_async_tools() -> dict[str, object]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return {"tool_registry": registry, "tool_executor": ToolExecutor()}


# --- AsyncProvider default contract ------------------------------------------------


class PlainAsyncProvider(AsyncProvider):
    async def generate(self, prompt: str) -> str:
        return f"async: {prompt}"


class ScriptedAsyncProvider(AsyncProvider):
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def generate(self, prompt: str) -> str:
        raise AssertionError("not used")

    async def generate_response(self, prompt, *, tools=(), tool_results=()):
        self.calls.append((prompt, tuple(tools), tuple(tool_results)))
        return TextResponse("scripted")


async def test_async_provider_default_stream_yields_single_final_event():
    provider = PlainAsyncProvider()
    events = []
    async for event in provider.stream_response("hi"):
        events.append(event)

    assert events == [TextResponse("async: hi")]


async def test_async_provider_default_stream_wraps_generate_response():
    provider = ScriptedAsyncProvider()
    tools = (ToolSpec("upper", "Upper."),)
    events = []
    async for event in provider.stream_response("hi", tools=tools):
        events.append(event)

    assert events == [TextResponse("scripted")]
    assert provider.calls == [("hi", tools, ())]


# --- SyncProviderAdapter bridge ------------------------------------------------------


async def test_adapter_bridges_sync_stream_events_in_order():
    adapter = SyncProviderAdapter(StreamingSyncProvider())
    events = []
    async for event in adapter.stream_response("hi"):
        events.append(event)

    assert events == [
        StreamTextDelta("Hel"),
        StreamTextDelta("lo"),
        TextResponse("Hello"),
    ]


async def test_adapter_stream_falls_back_to_generate_response_without_stream():
    provider = ScriptedProvider([TextResponse("scripted")])
    adapter = SyncProviderAdapter(provider)
    # ScriptedProvider inherits the Provider ABC default: no incremental deltas.
    events = []
    async for event in adapter.stream_response("hi"):
        events.append(event)

    assert events == [TextResponse("scripted")]


async def test_adapter_stream_surfaces_provider_errors():
    adapter = SyncProviderAdapter(ScriptedProvider([]))
    with pytest.raises(ProviderResponseError):
        async for _ in adapter.stream_response("hi"):
            pass


# --- AsyncAgent streaming loop --------------------------------------------------------


async def test_async_agent_forwards_deltas_in_order():
    provider = StreamingAsyncProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )
    agent = AsyncAgent(provider)

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert deltas == ["Hel", "lo"]
    assert result.success is True
    assert result.output == "Hello"


async def test_async_agent_with_on_delta_none_never_streams():
    provider = AsyncStreamlessProvider()
    agent = AsyncAgent(provider)
    result = await agent.run("hi")

    assert result.success is True
    assert result.output == "plain: hi"
    assert provider.generate_response_calls == 1


async def test_async_agent_streaming_tool_loop():
    provider = StreamingAsyncProvider(
        [
            [ToolCallRequest("echo", "hi")],
            [StreamTextDelta("echo: hi"), TextResponse("echo: hi")],
        ]
    )
    agent = AsyncAgent(provider, **make_async_tools())

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert deltas == ["echo: hi"]
    assert result.success is True
    assert result.output == "echo: hi"


async def test_async_agent_forwards_deltas_before_tool_request():
    provider = StreamingAsyncProvider(
        [
            [StreamTextDelta("Checking..."), ToolCallRequest("echo", "hi")],
            [TextResponse("Final answer")],
        ]
    )
    agent = AsyncAgent(provider, **make_async_tools())

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert deltas == ["Checking..."]
    assert result.output == "Final answer"


async def test_async_agent_stream_error_becomes_failed_result():
    class ExplodingAsyncProvider(AsyncProvider):
        async def generate(self, prompt: str) -> str:
            raise AssertionError("not used")

        async def stream_response(self, prompt, *, tools=(), tool_results=()):
            raise RuntimeError("backend hung up")
            yield  # pragma: no cover

    agent = AsyncAgent(ExplodingAsyncProvider())
    result = await agent.run("hi", on_delta=lambda text: None)

    assert result.success is False
    assert result.output == "provider error: backend hung up"


async def test_async_agent_stream_without_final_response_is_an_error():
    provider = StreamingAsyncProvider([[StreamTextDelta("only deltas")]])
    agent = AsyncAgent(provider)

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert deltas == ["only deltas"]
    assert result.success is False
    assert result.output == "provider error: provider stream ended without a final response"


async def test_async_agent_on_delta_exception_aborts_the_run():
    provider = StreamingAsyncProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )
    agent = AsyncAgent(provider)

    def broken_on_delta(text: str) -> None:
        raise ValueError("sink closed")

    result = await agent.run("hi", on_delta=broken_on_delta)

    assert result.success is False
    assert result.output == "provider error: sink closed"


# --- AsyncRuntime passthrough ---------------------------------------------------------


async def test_async_runtime_run_forwards_on_delta():
    provider = StreamingAsyncProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )
    runtime = AsyncRuntime(AsyncAgent(provider))

    deltas: list[str] = []
    result = await runtime.run("hi", on_delta=deltas.append)

    assert deltas == ["Hel", "lo"]
    assert result.output == "Hello"


async def test_async_runtime_run_without_on_delta_keeps_plain_path():
    provider = AsyncStreamlessProvider()
    runtime = AsyncRuntime(AsyncAgent(provider))
    result = await runtime.run("hi")

    assert result.output == "plain: hi"
    assert provider.generate_response_calls == 1


# --- Sync provider under AsyncAgent via adapter ----------------------------------------


async def test_sync_streaming_provider_drives_async_agent_through_adapter():
    provider = StreamingSyncProvider()
    agent = AsyncAgent(SyncProviderAdapter(provider))

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert provider.stream_calls == 1
    assert deltas == ["Hel", "lo"]
    assert result.output == "Hello"


async def test_sync_streaming_provider_runs_tool_loop_under_adapter():
    scripted = StreamingToolLoopSyncProvider()
    agent = AsyncAgent(SyncProviderAdapter(scripted), **make_async_tools())

    deltas: list[str] = []
    result = await agent.run("hi", on_delta=deltas.append)

    assert deltas == ["echo: hi"]
    assert result.output == "echo: hi"


class StreamingToolLoopSyncProvider(Provider):
    """A sync streaming provider scripted to request a tool then answer."""

    def __init__(self) -> None:
        self._position = 0

    def generate(self, prompt: str) -> str:
        raise AssertionError("generate() must not be called")

    def stream_response(
        self, prompt, *, tools=(), tool_results=()
    ) -> Iterator[ProviderStreamEvent]:
        self._position += 1
        if self._position == 1:
            yield ToolCallRequest("echo", "hi")
        else:
            yield StreamTextDelta("echo: hi")
            yield TextResponse("echo: hi")


# --- Adapter fallbacks for full branch coverage -------------------------------------


class BareSyncProvider:
    """Not a Provider subclass at all: only ``generate()`` exists."""

    def generate(self, prompt: str) -> str:
        return f"bare: {prompt}"


async def test_adapter_stream_falls_back_to_generate_for_bare_providers():
    adapter = SyncProviderAdapter(BareSyncProvider())
    events = []
    async for event in adapter.stream_response("hi"):
        events.append(event)

    assert events == [TextResponse("bare: hi")]
