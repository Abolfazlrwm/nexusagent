"""Contract tests for the async tool executor (ADR 0006)."""

from __future__ import annotations

import pytest

from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.tool import AsyncTool, Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.uppercase_tool import UppercaseTool


class UpperAsyncTool(AsyncTool):
    def __init__(self) -> None:
        super().__init__(name="upper_async", description="Uppercase input (async).")
        self.calls: list[str] = []

    async def aexecute(self, input_data: str) -> str:
        self.calls.append(input_data)
        return input_data.upper()


class BoomTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="boom", description="Always fails.")

    def execute(self, input_data: str) -> str:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_executes_sync_tools() -> None:
    assert await AsyncToolExecutor().execute(UppercaseTool(), "hi") == "HI"


@pytest.mark.asyncio
async def test_awaits_async_tools_natively() -> None:
    executor = AsyncToolExecutor()
    tool = UpperAsyncTool()

    assert await executor.execute(tool, "hi") == "HI"
    assert tool.calls == ["hi"]


@pytest.mark.asyncio
async def test_non_tool_instance_raises_type_error() -> None:
    with pytest.raises(TypeError, match="Tool instance"):
        await AsyncToolExecutor().execute("not a tool", "hi")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_non_string_input_raises_type_error_for_both_paths() -> None:
    executor = AsyncToolExecutor()
    async_tool = UpperAsyncTool()

    with pytest.raises(TypeError, match="Tool input must be a string"):
        await executor.execute(UppercaseTool(), 123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Tool input must be a string"):
        await executor.execute(async_tool, None)  # type: ignore[arg-type]

    assert async_tool.calls == []


@pytest.mark.asyncio
async def test_blank_input_raises_value_error_for_both_paths() -> None:
    executor = AsyncToolExecutor()
    async_tool = UpperAsyncTool()

    with pytest.raises(ValueError, match="must not be empty"):
        await executor.execute(UppercaseTool(), "   ")

    with pytest.raises(ValueError, match="must not be empty"):
        await executor.execute(async_tool, "")

    assert async_tool.calls == []


@pytest.mark.asyncio
async def test_sync_tool_failure_is_wrapped() -> None:
    with pytest.raises(ToolExecutionError, match="RuntimeError: boom") as info:
        await AsyncToolExecutor().execute(BoomTool(), "hi")

    assert isinstance(info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_async_tool_failure_is_wrapped() -> None:
    class BoomAsyncTool(AsyncTool):
        def __init__(self) -> None:
            super().__init__(name="boom_async", description="Always fails.")

        async def aexecute(self, input_data: str) -> str:
            raise ValueError("bad input")

    with pytest.raises(ToolExecutionError, match="ValueError: bad input") as info:
        await AsyncToolExecutor().execute(BoomAsyncTool(), "hi")

    assert isinstance(info.value.__cause__, ValueError)


def test_async_tool_execute_fails_fast_on_the_sync_path() -> None:
    with pytest.raises(NotImplementedError, match="cannot run on the sync path"):
        UpperAsyncTool().execute("hi")


def test_async_tool_through_the_sync_executor_is_a_clear_failure() -> None:
    with pytest.raises(ToolExecutionError, match="cannot run on the sync path"):
        ToolExecutor().execute(UpperAsyncTool(), "hi")
