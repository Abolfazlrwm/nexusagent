"""NexusAgent — a minimal, dependency-free agent runtime.

This module exposes the entire stable public API (1.0 stability contract,
ADR 0010). Every name listed in ``__all__`` is governed by semantic
versioning: within a major release nothing here is renamed, moved, or
removed, and new capabilities are only added. Everything else in
``nexusagent.*`` is internal and may change in any release.

Quick start: build a runtime with :func:`create_application_runtime` and
pass prompts to the returned :class:`Runtime` — see the README.

The import name is ``nexusagent`` (the distribution is
``nexusagent-runtime`` on PyPI).
"""

from nexusagent.agent import Agent, AgentResult
from nexusagent.application import create_application_runtime
from nexusagent.async_agent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.async_runtime import AsyncRuntime, create_async_runtime
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.config import Settings
from nexusagent.factory import create_provider
from nexusagent.memory import ConversationTurn, InMemoryMemory, Memory
from nexusagent.provider import (
    AsyncProvider,
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequestError,
    ProviderResponse,
    ProviderResponseError,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.providers import FakeProvider, ScriptedProvider
from nexusagent.runtime import Runtime, create_runtime
from nexusagent.tool import AsyncTool, Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry

__version__ = "1.2.0"

__all__ = [
    # Agent layer (sync and async)
    "Agent",
    "AgentResult",
    "AsyncAgent",
    "AsyncProvider",
    "AsyncRuntime",
    "AsyncTool",
    "AsyncToolExecutor",
    # Conversation memory (ADR 0012)
    "ConversationTurn",
    # Offline / testing providers
    "FakeProvider",
    # Conversation memory (ADR 0012), continued
    "InMemoryMemory",
    "Memory",
    # Provider contract and its typed errors
    "Provider",
    "ProviderConfig",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderRequestError",
    "ProviderResponse",
    "ProviderResponseError",
    "ProviderStreamEvent",
    "Runtime",
    "ScriptedProvider",
    # Configuration
    "Settings",
    "StreamTextDelta",
    # Sync-in-async bridge
    "SyncProviderAdapter",
    "TextResponse",
    # Tool layer
    "Tool",
    "ToolCallRequest",
    "ToolExecutionError",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    # Runtime factories
    "create_application_runtime",
    "create_async_runtime",
    "create_provider",
    "create_runtime",
]
