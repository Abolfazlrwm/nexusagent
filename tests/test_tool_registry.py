import os

import pytest

from nexusagent.tool import Tool
from nexusagent.tool_registry import ToolRegistry


class EchoTool(Tool):
    def execute(self, input_data: str) -> str:
        return input_data


class ExplodingTool(Tool):
    def execute(self, input_data: str) -> str:
        raise AssertionError("Tool must not be executed by the registry")


def make_echo_tool(name: str = "echo", description: str = "Echo input") -> EchoTool:
    return EchoTool(name=name, description=description)


def test_registry_can_be_constructed():
    registry = ToolRegistry()

    assert isinstance(registry, ToolRegistry)


def test_empty_registry_returns_empty_list():
    registry = ToolRegistry()

    assert registry.list_tools() == []


def test_register_valid_tool():
    registry = ToolRegistry()
    tool = make_echo_tool()

    registry.register(tool)

    assert registry.get("echo") is tool


def test_get_returns_exact_registered_instance():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    result = registry.get("echo")

    assert result is tool


def test_unregister_removes_tool():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    registry.unregister("echo")

    with pytest.raises(KeyError):
        registry.get("echo")


def test_get_missing_tool_raises_key_error():
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.get("missing")


def test_unregister_missing_tool_raises_key_error():
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.unregister("missing")


def test_register_same_instance_twice_raises_value_error():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    with pytest.raises(ValueError):
        registry.register(tool)


def test_register_duplicate_name_raises_value_error():
    registry = ToolRegistry()
    tool_a = make_echo_tool("echo", "Echo A")
    tool_b = make_echo_tool("echo", "Echo B")
    registry.register(tool_a)

    with pytest.raises(ValueError):
        registry.register(tool_b)


def test_original_tool_survives_failed_duplicate_registration():
    registry = ToolRegistry()
    tool_a = make_echo_tool("echo", "Echo A")
    tool_b = make_echo_tool("echo", "Echo B")
    registry.register(tool_a)

    with pytest.raises(ValueError):
        registry.register(tool_b)

    assert registry.get("echo") is tool_a


def test_list_tools_returns_tool_instances():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    tools = registry.list_tools()

    assert tools == [tool]
    assert isinstance(tools[0], Tool)


def test_list_tools_exposes_name_and_description():
    registry = ToolRegistry()
    tool = make_echo_tool(name="echo", description="Echo input")
    registry.register(tool)

    listed_tool = registry.list_tools()[0]

    assert listed_tool.name == "echo"
    assert listed_tool.description == "Echo input"


def test_list_tools_preserves_registration_order():
    registry = ToolRegistry()
    tool_a = make_echo_tool("a", "A")
    tool_b = make_echo_tool("b", "B")
    tool_c = make_echo_tool("c", "C")

    registry.register(tool_a)
    registry.register(tool_b)
    registry.register(tool_c)

    assert registry.list_tools() == [tool_a, tool_b, tool_c]


def test_list_tools_returns_defensive_copy():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    tools = registry.list_tools()
    tools.clear()

    assert registry.list_tools() == [tool]


def test_list_tools_returns_fresh_list_every_call():
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    first = registry.list_tools()
    second = registry.list_tools()

    assert first is not second
    assert first == second


def test_two_registries_are_isolated():
    registry_a = ToolRegistry()
    registry_b = ToolRegistry()
    tool = make_echo_tool()

    registry_a.register(tool)

    assert registry_a.get("echo") is tool
    with pytest.raises(KeyError):
        registry_b.get("echo")


def test_register_non_tool_raises_type_error():
    registry = ToolRegistry()

    with pytest.raises(TypeError):
        registry.register("not a tool")


def test_get_non_string_name_raises_type_error():
    registry = ToolRegistry()

    with pytest.raises(TypeError):
        registry.get(123)


def test_unregister_non_string_name_raises_type_error():
    registry = ToolRegistry()

    with pytest.raises(TypeError):
        registry.unregister(123)


def test_get_empty_name_raises_value_error():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.get("")


def test_get_whitespace_only_name_raises_value_error():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.get("   ")


def test_unregister_empty_name_raises_value_error():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.unregister("")


def test_unregister_whitespace_only_name_raises_value_error():
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.unregister("   ")


def test_registry_never_executes_tools():
    registry = ToolRegistry()
    tool = ExplodingTool(name="boom", description="Explodes if executed")

    registry.register(tool)
    registry.get("boom")
    registry.list_tools()
    registry.unregister("boom")

    with pytest.raises(KeyError):
        registry.get("boom")


def test_registry_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ToolRegistry must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)
    registry.get("echo")
    registry.list_tools()
    registry.unregister("echo")


def test_registry_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ToolRegistry must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)
    registry.get("echo")
    registry.list_tools()
    registry.unregister("echo")


def test_registry_works_without_any_nexus_environment_variables(monkeypatch):
    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)

    assert registry.get("echo") is tool


def test_names_are_not_silently_normalized():
    registry = ToolRegistry()
    tool = make_echo_tool(name=" echo ", description="Echo")
    registry.register(tool)

    assert registry.get(" echo ") is tool
    with pytest.raises(KeyError):
        registry.get("echo")


def test_unregister_then_register_preserves_expected_order():
    registry = ToolRegistry()
    tool_a = make_echo_tool("a", "A")
    tool_b = make_echo_tool("b", "B")
    tool_c = make_echo_tool("c", "C")

    registry.register(tool_a)
    registry.register(tool_b)
    registry.unregister("b")
    registry.register(tool_c)
    new_tool_b = make_echo_tool("b", "New B")
    registry.register(new_tool_b)

    assert registry.list_tools() == [tool_a, tool_c, new_tool_b]


def test_registry_has_no_global_shared_state():
    registry_a = ToolRegistry()
    tool = make_echo_tool()
    registry_a.register(tool)

    registry_b = ToolRegistry()

    assert registry_b.list_tools() == []


def test_tool_registry_module_does_not_import_forbidden_modules():
    import nexusagent.tool_registry as registry_module

    with open(registry_module.__file__, encoding="utf-8") as f:
        contents = f.read()

    for forbidden in (
        "nexusagent.agent",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
        "nexusagent.factory",
        "nexusagent.runtime",
        "nexusagent.main",
        "import socket",
        "import urllib",
        "import requests",
        "import pathlib",
        "os.environ",
    ):
        assert forbidden not in contents
