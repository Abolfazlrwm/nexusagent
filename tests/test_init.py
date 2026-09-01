import importlib

import nexusagent
from nexusagent import Agent, Runtime, Settings, create_application_runtime, create_runtime
from nexusagent.agent import Agent as AgentFromModule
from nexusagent.application import (
    create_application_runtime as create_application_runtime_from_module,
)
from nexusagent.config import Settings as SettingsFromModule
from nexusagent.runtime import Runtime as RuntimeFromModule
from nexusagent.runtime import create_runtime as create_runtime_from_module


def test_runtime_importable_from_package_root():
    assert Runtime is RuntimeFromModule


def test_create_runtime_importable_from_package_root():
    assert create_runtime is create_runtime_from_module


def test_agent_importable_from_package_root():
    assert Agent is AgentFromModule


def test_settings_importable_from_package_root():
    assert Settings is SettingsFromModule


def test_create_application_runtime_importable_from_package_root():
    assert create_application_runtime is create_application_runtime_from_module


def test_version_unchanged():
    assert nexusagent.__version__ == "0.1.0"


def test_all_contains_exactly_the_public_api():
    assert set(nexusagent.__all__) == {
        "Agent",
        "Runtime",
        "Settings",
        "create_application_runtime",
        "create_runtime",
    }


def test_public_api_does_not_expose_internal_implementation_details():
    exposed = set(dir(nexusagent))

    internal_only = {
        "ToolRegistry",
        "ToolExecutor",
        "ToolExecutionError",
        "Tool",
        "EchoTool",
        "UppercaseTool",
        "CalculatorTool",
        "Provider",
        "ProviderConfig",
        "ProviderError",
        "FakeProvider",
        "HttpProvider",
        "create_tool_registry",
        "create_tool_runtime",
        "create_provider",
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

    assert nexusagent.__version__ == "0.1.0"
