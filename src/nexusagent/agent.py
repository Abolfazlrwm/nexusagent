"""Agent Core for NexusAgent.

Defines the minimal contract for running an agent: input text in,
an AgentResult out. The Agent delegates generation to a Provider.
It can also optionally coordinate explicit tool execution through
an injected ToolRegistry and ToolExecutor.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexusagent.provider import Provider
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


@dataclass(frozen=True)
class AgentResult:
    """The result of a single agent run."""

    output: str
    success: bool


class Agent:
    def __init__(
        self,
        provider: Provider,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor

    def run(self, input_text: str) -> AgentResult:
        """Run the agent on the given input and return an AgentResult."""
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        try:
            output = self.provider.generate(input_text)
        except Exception as exc:  # noqa: BLE001
            return AgentResult(output=f"provider error: {exc}", success=False)

        return AgentResult(output=output, success=True)

    def execute_tool(self, tool_name: str, input_data: str) -> str:
        """Execute a specific, explicitly named tool and return its output."""
        if self.tool_registry is None:
            raise RuntimeError("Agent requires a ToolRegistry to execute tools")

        if self.tool_executor is None:
            raise RuntimeError("Agent requires a ToolExecutor to execute tools")

        tool = self.tool_registry.get(tool_name)
        return self.tool_executor.execute(tool, input_data)
