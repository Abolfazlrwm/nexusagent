from nexusagent.calculator_tool import CalculatorTool
from nexusagent.echo_tool import EchoTool
from nexusagent.tool_factory import create_tool_registry
from nexusagent.tool_registry import ToolRegistry
from nexusagent.uppercase_tool import UppercaseTool


def test_create_tool_registry_returns_a_tool_registry():
    registry = create_tool_registry()

    assert isinstance(registry, ToolRegistry)


def test_create_tool_registry_contains_expected_tool_names():
    registry = create_tool_registry()

    names = [tool.name for tool in registry.list_tools()]

    assert names == ["echo", "uppercase", "calculator"]


def test_create_tool_registry_preserves_registration_order():
    registry = create_tool_registry()

    tools = registry.list_tools()

    assert isinstance(tools[0], EchoTool)
    assert isinstance(tools[1], UppercaseTool)
    assert isinstance(tools[2], CalculatorTool)


def test_create_tool_registry_tools_have_expected_descriptions():
    registry = create_tool_registry()

    echo_tool = registry.get("echo")
    uppercase_tool = registry.get("uppercase")
    calculator_tool = registry.get("calculator")

    assert echo_tool.description == "Returns its input unchanged."
    assert uppercase_tool.description == "Converts input to uppercase."
    assert calculator_tool.description == "Performs basic arithmetic operations."


def test_create_tool_registry_tools_are_retrievable_by_name():
    registry = create_tool_registry()

    assert isinstance(registry.get("echo"), EchoTool)
    assert isinstance(registry.get("uppercase"), UppercaseTool)
    assert isinstance(registry.get("calculator"), CalculatorTool)


def test_create_tool_registry_returns_fresh_registry_each_call():
    registry1 = create_tool_registry()
    registry2 = create_tool_registry()

    assert registry1 is not registry2


def test_create_tool_registry_does_not_share_tool_instances_across_calls():
    registry1 = create_tool_registry()
    registry2 = create_tool_registry()

    assert registry1.get("echo") is not registry2.get("echo")
    assert registry1.get("uppercase") is not registry2.get("uppercase")
    assert registry1.get("calculator") is not registry2.get("calculator")


def test_create_tool_registry_does_not_execute_tools(monkeypatch):
    def fail_if_called(self, input_data):
        raise AssertionError("create_tool_registry() must not execute any tool")

    monkeypatch.setattr(EchoTool, "execute", fail_if_called)
    monkeypatch.setattr(UppercaseTool, "execute", fail_if_called)
    monkeypatch.setattr(CalculatorTool, "execute", fail_if_called)

    create_tool_registry()


def test_create_tool_registry_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_tool_registry() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_tool_registry()


def test_create_tool_registry_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_tool_registry() must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    create_tool_registry()


def test_create_tool_registry_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    registry = create_tool_registry()

    assert [tool.name for tool in registry.list_tools()] == ["echo", "uppercase", "calculator"]
