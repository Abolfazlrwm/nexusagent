"""Async execution of tools.

``AsyncToolExecutor`` is the async mirror of :class:`nexusagent.tool_executor.
ToolExecutor`:

- ``AsyncTool`` instances are awaited natively through ``aexecute()``.
- Plain sync tools run unchanged in a worker thread via the sync executor,
  so validation and ``ToolExecutionError`` wrapping are identical on both
  paths (ADR 0006).
"""

from __future__ import annotations

import asyncio

from nexusagent.tool import AsyncTool, Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor

__all__ = ["AsyncToolExecutor"]


class AsyncToolExecutor:
    """Execute sync and async tools from a running event loop."""

    def __init__(self) -> None:
        self._sync_executor = ToolExecutor()

    async def execute(self, tool: Tool, input_data: str) -> str:
        if not isinstance(tool, Tool):
            raise TypeError("ToolExecutor requires a Tool instance")

        if isinstance(tool, AsyncTool):
            return await self._execute_async(tool, input_data)

        return await asyncio.to_thread(self._sync_executor.execute, tool, input_data)

    async def _execute_async(self, tool: AsyncTool, input_data: str) -> str:
        """Run an ``AsyncTool`` with the sync executor's validation contract."""
        if not isinstance(input_data, str):
            raise TypeError("Tool input must be a string")

        if not input_data.strip():
            raise ValueError("Tool input must not be empty or whitespace-only")

        try:
            return await tool.aexecute(input_data)
        except Exception as exc:
            # Same wrapping as the sync executor: the original class stays in
            # the message and the exception itself becomes the cause.
            raise ToolExecutionError(f"{type(exc).__name__}: {exc}") from exc
