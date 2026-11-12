"""Async runtime facade and its factory.

``AsyncRuntime`` mirrors :class:`nexusagent.runtime.Runtime` over
``AsyncAgent``; ``create_async_runtime()`` mirrors ``create_runtime()``,
wrapping the provider chosen by the factory in
:class:`nexusagent.async_provider.SyncProviderAdapter` so every configured
backend works under the event loop unchanged (ADR 0006).
"""

from __future__ import annotations

from nexusagent.agent import AgentResult
from nexusagent.async_agent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.config import Settings
from nexusagent.factory import create_provider
from nexusagent.provider import ProviderConfig
from nexusagent.tool import Tool
from nexusagent.tool_registry import ToolRegistry

__all__ = ["AsyncRuntime", "create_async_runtime"]


class AsyncRuntime:
    def __init__(
        self,
        agent: AsyncAgent,
        tool_registry: ToolRegistry | None = None,
        tool_executor: AsyncToolExecutor | None = None,
    ) -> None:
        self.agent = agent
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor

    async def run(self, input_text: str) -> AgentResult:
        return await self.agent.run(input_text)

    async def execute_tool(self, tool_name: str, input_data: str) -> str:
        return await self.agent.execute_tool(tool_name, input_data)

    def list_tools(self) -> list[Tool]:
        if self.tool_registry is None:
            raise RuntimeError("AsyncRuntime requires a ToolRegistry to list tools")

        return self.tool_registry.list_tools()


def create_async_runtime(
    settings: Settings | None = None,
    tool_registry: ToolRegistry | None = None,
    tool_executor: AsyncToolExecutor | None = None,
) -> AsyncRuntime:
    if settings is None:
        settings = Settings.from_env()

    settings.validate()

    config = ProviderConfig(
        model=settings.model,
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        timeout=settings.timeout,
    )
    provider = SyncProviderAdapter(create_provider(settings.provider, config))
    agent = AsyncAgent(provider, tool_registry=tool_registry, tool_executor=tool_executor)
    return AsyncRuntime(agent, tool_registry=tool_registry, tool_executor=tool_executor)
