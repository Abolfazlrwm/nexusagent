"""Run the async tool loop end to end, offline — no API key, no internet.

A scripted "model backend" requests a tool call; the async agent awaits an
``AsyncTool`` for the answer, feeds the result back, and finishes with text.
Sync providers keep working under the event loop through
``SyncProviderAdapter`` (see ADR 0006).

Run from the repository root:

    python examples/async_tool_loop.py
"""

from __future__ import annotations

import asyncio

from nexusagent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.provider import TextResponse, ToolCallRequest
from nexusagent.providers import ScriptedProvider
from nexusagent.tool import AsyncTool
from nexusagent.tool_registry import ToolRegistry


class SlowUppercaseTool(AsyncTool):
    """Uppercase the input — the await stands in for any real async work."""

    def __init__(self) -> None:
        super().__init__(name="upper", description="Uppercase the given text.")

    async def aexecute(self, input_data: str) -> str:
        await asyncio.sleep(0.05)  # simulate awaited work (I/O, debounce, ...)
        return input_data.upper()


async def main() -> None:
    backend = ScriptedProvider(
        [
            ToolCallRequest("upper", "nexusagent"),
            TextResponse("NEXUSAGENT"),
        ]
    )
    registry = ToolRegistry()
    registry.register(SlowUppercaseTool())

    agent = AsyncAgent(
        SyncProviderAdapter(backend),  # any sync provider works under the loop
        tool_registry=registry,
        tool_executor=AsyncToolExecutor(),
    )

    result = await agent.run("Make this uppercase: nexusagent")
    print(result.output)  # NEXUSAGENT
    print(result.success)  # True


if __name__ == "__main__":
    asyncio.run(main())
