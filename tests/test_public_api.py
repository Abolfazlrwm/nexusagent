"""Pin the stable public API surface (ADR 0010).

``nexusagent.__all__`` IS the 1.0 stability contract: every name in it is
governed by semantic versioning, everything else in ``nexusagent.*`` is
internal. These tests pin the surface so an accidental removal, rename or
silent addition fails CI, and so every exported name is actually usable
from the top-level import.
"""

from __future__ import annotations

import re
import types

import nexusagent

EXPECTED_PUBLIC_API = (
    # Agent layer (sync and async)
    "Agent",
    "AgentResult",
    # Multi-agent orchestration (ADR 0015)
    "AgentTeam",
    "AsyncAgent",
    "AsyncProvider",
    "AsyncRuntime",
    "AsyncTool",
    "AsyncToolExecutor",
    # Conversation memory (ADR 0012)
    "ConversationTurn",
    # Offline demo brain (ADR 0016)
    "DemoProvider",
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
    # Persistent conversation memory (ADR 0013)
    "SQLiteMemory",
    "ScriptedProvider",
    # Configuration
    "Settings",
    "StreamTextDelta",
    # Sync-in-async bridge
    "SyncProviderAdapter",
    # Multi-agent orchestration (ADR 0015)
    "TeamResult",
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
    "create_provider_router",
    "create_runtime",
)


def test_public_api_matches_pinned_surface() -> None:
    """__all__ must equal the pinned surface exactly: no less, no more."""
    assert nexusagent.__all__ == list(EXPECTED_PUBLIC_API)


def test_every_exported_name_resolves_at_top_level() -> None:
    """Every name in __all__ must be importable as ``nexusagent.<name>``."""
    missing = [name for name in nexusagent.__all__ if not hasattr(nexusagent, name)]
    assert missing == []


def _defined_in_package(obj: object) -> bool:
    """True if obj is defined inside nexusagent.

    Union-type aliases (``X | Y``) are instances of ``types.UnionType`` with
    ``__module__ == "types"``; for those, every member class must be defined
    inside nexusagent instead.
    """
    if isinstance(obj, types.UnionType):
        members = getattr(obj, "__args__", ())
        return bool(members) and all(
            getattr(member, "__module__", "").startswith("nexusagent") for member in members
        )

    module = getattr(obj, "__module__", "")
    return module.startswith("nexusagent")


def test_every_exported_name_defined_in_package() -> None:
    """No foreign re-exports: each name must be defined inside nexusagent."""
    foreign = [
        name for name in nexusagent.__all__ if not _defined_in_package(getattr(nexusagent, name))
    ]
    assert foreign == []


def test_documented_names_are_not_duplicated() -> None:
    assert len(nexusagent.__all__) == len(set(nexusagent.__all__))


def test_version_is_release_format() -> None:
    """__version__ must be a plain MAJOR.MINOR.PATCH string."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", nexusagent.__version__) is not None
