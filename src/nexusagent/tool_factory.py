from __future__ import annotations

from nexusagent.calculator_tool import CalculatorTool
from nexusagent.echo_tool import EchoTool
from nexusagent.tool_registry import ToolRegistry
from nexusagent.uppercase_tool import UppercaseTool


def create_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(UppercaseTool())
    registry.register(CalculatorTool())
    return registry
