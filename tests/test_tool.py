import os

import pytest

from nexusagent.tool import Tool


class EchoTool(Tool):
    def execute(self, input_data: str) -> str:
        return input_data


def make_echo_tool() -> EchoTool:
    return EchoTool(name="echo", description="Returns its input unchanged.")


def test_tool_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Tool(name="tool", description="a tool")


def test_concrete_tool_can_be_instantiated():
    tool = make_echo_tool()

    assert isinstance(tool, Tool)


def test_tool_name_is_available():
    tool = make_echo_tool()

    assert tool.name == "echo"


def test_tool_description_is_available():
    tool = make_echo_tool()

    assert tool.description == "Returns its input unchanged."


def test_tool_execute_returns_input_unchanged():
    tool = make_echo_tool()

    result = tool.execute("hello")

    assert result == "hello"


def test_tool_execute_preserves_surrounding_whitespace():
    tool = make_echo_tool()

    result = tool.execute(" hello ")

    assert result == " hello "


def test_tool_two_executions_are_independent():
    tool = make_echo_tool()

    result1 = tool.execute("first")
    result2 = tool.execute("second")

    assert result1 == "first"
    assert result2 == "second"


def test_tool_name_must_be_a_string():
    with pytest.raises(TypeError):
        EchoTool(name=123, description="a tool")


def test_tool_name_must_not_be_empty():
    with pytest.raises(ValueError):
        EchoTool(name="", description="a tool")


def test_tool_name_must_not_be_whitespace_only():
    with pytest.raises(ValueError):
        EchoTool(name="   ", description="a tool")


def test_tool_description_must_be_a_string():
    with pytest.raises(TypeError):
        EchoTool(name="echo", description=123)


def test_tool_description_must_not_be_empty():
    with pytest.raises(ValueError):
        EchoTool(name="echo", description="")


def test_tool_description_must_not_be_whitespace_only():
    with pytest.raises(ValueError):
        EchoTool(name="echo", description="   ")


def test_tool_description_preserves_surrounding_whitespace():
    tool = EchoTool(name="echo", description=" My tool ")

    assert tool.description == " My tool "


def test_tool_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Tool must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    tool = make_echo_tool()
    tool.execute("hello")


def test_tool_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Tool must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    tool = make_echo_tool()
    tool.execute("hello")


def test_tool_works_without_any_nexus_environment_variables(monkeypatch):
    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    tool = make_echo_tool()
    result = tool.execute("hello")

    assert result == "hello"


def test_tool_module_does_not_import_agent_provider_or_runtime():
    import nexusagent.tool as tool_module

    source = tool_module.__file__
    with open(source, encoding="utf-8") as f:
        contents = f.read()

    for forbidden in ("nexusagent.agent", "nexusagent.provider", "nexusagent.runtime"):
        assert forbidden not in contents
