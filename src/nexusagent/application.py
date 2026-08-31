from __future__ import annotations

from nexusagent.config import Settings
from nexusagent.runtime import Runtime
from nexusagent.runtime_factory import create_tool_runtime


def create_application_runtime(settings: Settings | None = None) -> Runtime:
    return create_tool_runtime(settings)
