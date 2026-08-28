from __future__ import annotations

from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
from nexusagent.factory import create_provider
from nexusagent.provider import ProviderConfig
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class Runtime:
    def __init__(
        self,
        agent: Agent,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.agent = agent
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor

    def run(self, input_text: str) -> AgentResult:
        return self.agent.run(input_text)

    def execute_tool(self, tool_name: str, input_data: str) -> str:
        return self.agent.execute_tool(tool_name, input_data)

    def list_tools(self) -> list[Tool]:
        if self.tool_registry is None:
            raise RuntimeError("Runtime requires a ToolRegistry to list tools")

        return self.tool_registry.list_tools()


def create_runtime(
    settings: Settings | None = None,
    tool_registry: ToolRegistry | None = None,
    tool_executor: ToolExecutor | None = None,
) -> Runtime:
    if settings is None:
        settings = Settings.from_env()

    settings.validate()

    config = ProviderConfig(
        model=settings.model,
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        timeout=settings.timeout,
    )
    provider = create_provider(settings.provider, config)
    agent = Agent(provider, tool_registry=tool_registry, tool_executor=tool_executor)
    return Runtime(agent, tool_registry=tool_registry, tool_executor=tool_executor)
