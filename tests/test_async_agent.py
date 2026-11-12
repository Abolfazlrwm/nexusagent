"""Contract tests for the async agent loop (ADR 0006)."""

from __future__ import annotations

import asyncio

import pytest

from nexusagent.agent import DEFAULT_MAX_ITERATIONS, AgentResult
from nexusagent.async_agent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.provider import (
    AsyncProvider,
    ProviderResponse,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.providers import FakeProvider, ScriptedProvider
from nexusagent.tool import AsyncTool
from nexusagent.tool_executor import ToolExecutionError
from nexusagent.tool_registry import ToolRegistry
from nexusagent.uppercase_tool import UppercaseTool

pytestmark = pytest.mark.asyncio


class UpperAsyncTool(AsyncTool):
    def __init__(self) -> None:
        super().__init__(name="upper_async", description="Uppercase input (async).")

    async def aexecute(self, input_data: str) -> str:
        return input_data.upper()


class BoomTool(UppercaseTool):
    def execute(self, input_data: str) -> str:
        raise ToolExecutionError("uppercase is broken")


class EvilAsyncProvider(AsyncProvider):
    async def generate(self, prompt: str) -> str:
        return "never called"

    async def generate_response(
        self,
        prompt: str,
        *,
        tools: tuple[ToolSpec, ...] = (),
        tool_results: tuple[ToolResult, ...] = (),
    ) -> ProviderResponse:
        return object()  # type: ignore[return-value]


def make_agent(
    responses: list[ProviderResponse],
    tool: UppercaseTool | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AsyncAgent:
    registry: ToolRegistry | None = None
    executor: AsyncToolExecutor | None = None
    if tool is not None:
        registry = ToolRegistry()
        registry.register(tool)
        executor = AsyncToolExecutor()

    return AsyncAgent(
        SyncProviderAdapter(ScriptedProvider(responses)),
        tool_registry=registry,
        tool_executor=executor,
        max_iterations=max_iterations,
    )


async def test_default_max_iterations_matches_the_sync_agent() -> None:
    agent = make_agent([TextResponse("hi")])
    assert agent.max_iterations == DEFAULT_MAX_ITERATIONS == 10


async def test_text_only_run() -> None:
    result = await make_agent([TextResponse("hello")]).run("hi")
    assert result == AgentResult(output="hello", success=True)


async def test_run_with_a_provider_that_has_no_generate_response() -> None:
    agent = AsyncAgent(SyncProviderAdapter(FakeProvider()))
    result = await agent.run("hi")
    assert result == AgentResult(output="fake response: hi", success=True)


async def test_tool_loop_with_a_sync_tool() -> None:
    scripted = ScriptedProvider([ToolCallRequest("uppercase", "hi"), TextResponse("done")])
    agent = AsyncAgent(
        SyncProviderAdapter(scripted),
        tool_registry=_registry_with(UppercaseTool()),
        tool_executor=AsyncToolExecutor(),
    )

    result = await agent.run("shout")

    assert result == AgentResult(output="done", success=True)
    assert scripted.calls[1][2] == (ToolResult("uppercase", "hi", "HI"),)


async def test_tool_loop_with_an_async_tool() -> None:
    result = await make_agent(
        [ToolCallRequest("upper_async", "hi"), TextResponse("done")],
        tool=UpperAsyncTool(),
    ).run("shout")
    assert result == AgentResult(output="done", success=True)


async def test_failed_tool_result_is_fed_back() -> None:
    scripted = ScriptedProvider([ToolCallRequest("uppercase", "hi"), TextResponse("recovered")])
    agent = AsyncAgent(
        SyncProviderAdapter(scripted),
        tool_registry=_registry_with(BoomTool()),
        tool_executor=AsyncToolExecutor(),
    )

    result = await agent.run("shout")

    assert result == AgentResult(output="recovered", success=True)
    feedback = scripted.calls[1][2][0]
    assert isinstance(feedback, ToolResult)
    assert feedback.is_error is True
    assert "uppercase is broken" in feedback.output


async def test_unregistered_tool_becomes_an_error_result() -> None:
    result = await make_agent(
        [ToolCallRequest("missing", "x"), TextResponse("ok")],
        tool=UppercaseTool(),
    ).run("go")

    assert result.success is True
    assert result.output == "ok"


async def test_tool_request_without_tools_configured_fails_cleanly() -> None:
    result = await make_agent([ToolCallRequest("uppercase", "hi")]).run("go")

    assert result.success is False
    assert "provider requested tool 'uppercase'" in result.output
    assert "no tools configured" in result.output


async def test_loop_stops_at_max_iterations() -> None:
    agent = make_agent([ToolCallRequest("uppercase", "hi")], tool=UppercaseTool(), max_iterations=1)

    result = await agent.run("go")

    assert result.success is False
    assert result.output == "agent stopped: exceeded the maximum of 1 iterations"


async def test_provider_error_becomes_a_failed_result() -> None:
    result = await make_agent([]).run("go")

    assert result.success is False
    assert result.output.startswith("provider error: ")
    assert "ScriptedProvider has no more scripted responses" in result.output


async def test_unexpected_response_type_becomes_a_failed_result() -> None:
    agent = AsyncAgent(EvilAsyncProvider())
    result = await agent.run("go")

    assert result.success is False
    assert result.output == "provider error: unexpected response type object"


async def test_input_must_be_a_non_empty_string() -> None:
    agent = make_agent([TextResponse("hi")])

    with pytest.raises(TypeError, match="input_text must be a string"):
        await agent.run(123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must not be empty"):
        await agent.run("   ")


async def test_max_iterations_is_validated() -> None:
    provider = SyncProviderAdapter(FakeProvider())

    with pytest.raises(TypeError, match="max_iterations must be an integer"):
        AsyncAgent(provider, max_iterations=True)

    with pytest.raises(TypeError, match="max_iterations must be an integer"):
        AsyncAgent(provider, max_iterations="3")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="at least 1"):
        AsyncAgent(provider, max_iterations=0)


async def test_provider_must_be_an_async_provider() -> None:
    with pytest.raises(TypeError, match="AsyncProvider instance"):
        AsyncAgent(FakeProvider())  # type: ignore[arg-type]


async def test_execute_tool_runs_the_named_tool() -> None:
    agent = make_agent([TextResponse("hi")], tool=UppercaseTool())
    assert await agent.execute_tool("uppercase", "hi") == "HI"


async def test_execute_tool_requires_registry_and_executor() -> None:
    bare = make_agent([TextResponse("hi")])

    with pytest.raises(RuntimeError, match="requires a ToolRegistry"):
        await bare.execute_tool("uppercase", "hi")

    registry = ToolRegistry()
    registry.register(UppercaseTool())
    no_executor = AsyncAgent(SyncProviderAdapter(FakeProvider()), tool_registry=registry)

    with pytest.raises(RuntimeError, match="requires an AsyncToolExecutor"):
        await no_executor.execute_tool("uppercase", "hi")


async def test_execute_tool_propagates_key_error_for_unknown_names() -> None:
    agent = make_agent([TextResponse("hi")], tool=UppercaseTool())

    with pytest.raises(KeyError, match="'missing'"):
        await agent.execute_tool("missing", "hi")


async def test_has_tool_checks_the_registry() -> None:
    agent = make_agent([TextResponse("hi")], tool=UppercaseTool())

    assert agent.has_tool("uppercase") is True
    assert agent.has_tool("nope") is False


async def test_has_tool_requires_a_registry() -> None:
    with pytest.raises(RuntimeError, match="requires a ToolRegistry"):
        make_agent([TextResponse("hi")]).has_tool("upper")


async def test_concurrent_runs_are_independent() -> None:
    first = make_agent([TextResponse("one")])
    second = make_agent(
        [ToolCallRequest("upper_async", "two"), TextResponse("TWO")], tool=UpperAsyncTool()
    )

    results = await asyncio.gather(first.run("go"), second.run("go"))

    assert results == [
        AgentResult(output="one", success=True),
        AgentResult(output="TWO", success=True),
    ]


def _registry_with(tool: UppercaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(tool)
    return registry
