from __future__ import annotations

from nexusagent.config import Settings
from nexusagent.runtime import Runtime, create_runtime
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_factory import create_tool_registry


def create_tool_runtime(settings: Settings | None = None) -> Runtime:
    registry = create_tool_registry()
    executor = ToolExecutor()
    return create_runtime(settings, tool_registry=registry, tool_executor=executor)
