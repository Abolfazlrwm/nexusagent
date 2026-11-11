"""Contract tests for the async runtime facade and factory (ADR 0006)."""

from __future__ import annotations

import pytest

from nexusagent.agent import AgentResult
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_runtime import AsyncRuntime, create_async_runtime
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.config import Settings
from nexusagent.provider import TextResponse, ToolCallRequest
from nexusagent.providers import ScriptedProvider
from nexusagent.tool_registry import ToolRegistry
from nexusagent.uppercase_tool import UppercaseTool

pytestmark = pytest.mark.asyncio


def _uppercase_runtime() -> AsyncRuntime:
    registry = ToolRegistry()
    registry.register(UppercaseTool())
    return create_async_runtime(
        Settings(provider="fake"), tool_registry=registry, tool_executor=AsyncToolExecutor()
    )


async def test_default_runtime_uses_the_offline_fake_provider() -> None:
    runtime = create_async_runtime()
    result = await runtime.run("Hello Async")

    assert result == AgentResult(output="fake response: Hello Async", success=True)


async def test_explicit_settings_are_used() -> None:
    runtime = create_async_runtime(Settings(provider="fake"))
    assert await runtime.run("hi") == AgentResult(output="fake response: hi", success=True)


async def test_invalid_settings_are_rejected_before_any_run() -> None:
    with pytest.raises(ValueError, match="OpenAI provider requires a model"):
        create_async_runtime(Settings(provider="openai"))


async def test_runtime_composes_registry_and_executor() -> None:
    runtime = _uppercase_runtime()

    assert [t.name for t in runtime.list_tools()] == ["uppercase"]
    assert await runtime.execute_tool("uppercase", "hi") == "HI"
    assert await runtime.run("go") == AgentResult(output="fake response: go", success=True)


async def test_tool_executor_is_passed_through_unchanged() -> None:
    registry = ToolRegistry()
    registry.register(UppercaseTool())
    executor = AsyncToolExecutor()

    runtime = create_async_runtime(Settings(provider="fake"), registry, executor)

    assert runtime.tool_registry is registry
    assert runtime.tool_executor is executor


async def test_full_tool_loop_through_a_manually_composed_runtime() -> None:
    scripted = ScriptedProvider([ToolCallRequest("uppercase", "hi"), TextResponse("done")])
    registry = ToolRegistry()
    registry.register(UppercaseTool())

    from nexusagent.async_agent import AsyncAgent

    runtime = AsyncRuntime(
        AsyncAgent(
            SyncProviderAdapter(scripted), tool_registry=registry, tool_executor=AsyncToolExecutor()
        ),
        tool_registry=registry,
    )

    assert await runtime.run("shout") == AgentResult(output="done", success=True)
    assert scripted.calls[1][2][0].output == "HI"


async def test_list_tools_requires_a_registry() -> None:
    with pytest.raises(RuntimeError, match="requires a ToolRegistry"):
        create_async_runtime().list_tools()


async def test_execute_tool_requires_registry_and_executor() -> None:
    runtime = create_async_runtime()

    with pytest.raises(RuntimeError, match="requires a ToolRegistry"):
        await runtime.execute_tool("uppercase", "hi")
