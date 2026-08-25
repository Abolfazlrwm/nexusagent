from __future__ import annotations

from nexusagent.tool import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("ToolRegistry requires a Tool instance")

        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        self._validate_name(name)

        if name not in self._tools:
            raise KeyError(f"Tool {name!r} is not registered")

        return self._tools[name]

    def unregister(self, name: str) -> None:
        self._validate_name(name)

        if name not in self._tools:
            raise KeyError(f"Tool {name!r} is not registered")

        del self._tools[name]

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str):
            raise TypeError("Tool name must be a string")

        if not name.strip():
            raise ValueError("Tool name must not be empty or whitespace-only")
