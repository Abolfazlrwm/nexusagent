import importlib

import nexusagent
from nexusagent import (
    Agent,
    AgentResult,
    AsyncAgent,
    AsyncRuntime,
    Runtime,
    Settings,
    create_application_runtime,
    create_async_runtime,
    create_runtime,
)
from nexusagent.agent import Agent as AgentFromModule
from nexusagent.agent import AgentResult as AgentResultFromModule
from nexusagent.application import (
    create_application_runtime as create_application_runtime_from_module,
)
from nexusagent.async_agent import AsyncAgent as AsyncAgentFromModule
from nexusagent.async_runtime import AsyncRuntime as AsyncRuntimeFromModule
from nexusagent.async_runtime import create_async_runtime as create_async_runtime_from_module
from nexusagent.config import Settings as SettingsFromModule
from nexusagent.runtime import Runtime as RuntimeFromModule
from nexusagent.runtime import create_runtime as create_runtime_from_module


def test_runtime_importable_from_package_root():
    assert Runtime is RuntimeFromModule


def test_create_runtime_importable_from_package_root():
    assert create_runtime is create_runtime_from_module


def test_agent_importable_from_package_root():
    assert Agent is AgentFromModule


def test_agent_result_importable_from_package_root():
    assert AgentResult is AgentResultFromModule


def test_settings_importable_from_package_root():
    assert Settings is SettingsFromModule


def test_create_application_runtime_importable_from_package_root():
    assert create_application_runtime is create_application_runtime_from_module


def test_async_agent_importable_from_package_root():
    assert AsyncAgent is AsyncAgentFromModule


def test_async_runtime_importable_from_package_root():
    assert AsyncRuntime is AsyncRuntimeFromModule


def test_create_async_runtime_importable_from_package_root():
    assert create_async_runtime is create_async_runtime_from_module


def test_version_unchanged():
    assert nexusagent.__version__ == importlib.metadata.version("nexusagent-runtime")


def test_all_surface_is_pinned_elsewhere():
    """The exact __all__ surface is pinned by tests/test_public_api.py (ADR 0010).

    Since 1.0 the top-level facade IS the full public API; the single source
    of truth for its exact contents lives in test_public_api.py.
    """
    assert len(nexusagent.__all__) > 0
    assert all(isinstance(name, str) for name in nexusagent.__all__)


def test_public_api_does_not_expose_internal_implementation_details():
    """Vendor adapters, built-in demo tools and internal factories stay internal.

    ADR 0010: since 1.0 the top-level package exposes the full stable public
    API, but the concrete wire adapters (constructed via ``create_provider``
    or ``Settings``), the built-in demo tools and the internal tool factories
    are deliberately NOT re-exported at the top level.
    """
    exposed = set(dir(nexusagent))

    internal_only = {
        # Built-in demo tools (users register their own Tool subclasses)
        "EchoTool",
        "UppercaseTool",
        "CalculatorTool",
        # Wire adapters — construct via create_provider() / Settings
        "HttpProvider",
        "OpenAIProvider",
        "AnthropicProvider",
        "GeminiProvider",
        # Internal factories layered under the public runtime factories
        "create_tool_registry",
        "create_tool_runtime",
    }

    assert not (exposed & internal_only)


def test_import_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("importing nexusagent must not open network connections")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    importlib.reload(nexusagent)


def test_import_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("importing nexusagent must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    importlib.reload(nexusagent)


def test_import_does_not_construct_a_runtime(monkeypatch):
    from nexusagent import application as application_module

    def fail_if_called(*args, **kwargs):
        raise AssertionError("importing nexusagent must not construct a Runtime")

    monkeypatch.setattr(application_module, "create_application_runtime", fail_if_called)

    importlib.reload(nexusagent)


def test_import_does_not_require_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    importlib.reload(nexusagent)

    assert nexusagent.__version__ == importlib.metadata.version("nexusagent-runtime")
