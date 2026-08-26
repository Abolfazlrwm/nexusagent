from __future__ import annotations

from nexusagent.tool import Tool


class ToolExecutionError(Exception):
    """Raised when a Tool's execute() call fails."""


class ToolExecutor:
    def execute(self, tool: Tool, input_data: str) -> str:
        if not isinstance(tool, Tool):
            raise TypeError("ToolExecutor requires a Tool instance")

        if not isinstance(input_data, str):
            raise TypeError("Tool input must be a string")

        if not input_data.strip():
            raise ValueError("Tool input must not be empty or whitespace-only")

        try:
            return tool.execute(input_data)
        except Exception as exc:
            raise ToolExecutionError(str(exc)) from exc
