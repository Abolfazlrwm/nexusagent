from nexusagent.echo_tool import EchoTool
from nexusagent.tool import Tool


def test_echo_tool_is_a_tool():
    tool = EchoTool()

    assert isinstance(tool, Tool)


def test_echo_tool_has_stable_name():
    tool = EchoTool()

    assert tool.name == "echo"


def test_echo_tool_has_description():
    tool = EchoTool()

    assert isinstance(tool.description, str)
    assert tool.description.strip() != ""


def test_echo_tool_returns_input_unchanged():
    tool = EchoTool()

    result = tool.execute("hello world")

    assert result == "hello world"


def test_echo_tool_preserves_surrounding_whitespace():
    tool = EchoTool()

    result = tool.execute("  hello  ")

    assert result == "  hello  "


def test_echo_tool_is_deterministic():
    tool = EchoTool()

    assert tool.execute("same input") == tool.execute("same input")


def test_echo_tool_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("EchoTool must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    tool = EchoTool()
    tool.execute("hello")


def test_echo_tool_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("EchoTool must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    tool = EchoTool()
    tool.execute("hello")


def test_echo_tool_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    tool = EchoTool()

    assert tool.execute("hello") == "hello"
