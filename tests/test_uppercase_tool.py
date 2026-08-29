from nexusagent.tool import Tool
from nexusagent.uppercase_tool import UppercaseTool


def test_uppercase_tool_is_a_tool():
    tool = UppercaseTool()

    assert isinstance(tool, Tool)


def test_uppercase_tool_has_stable_name():
    tool = UppercaseTool()

    assert tool.name == "uppercase"


def test_uppercase_tool_has_description():
    tool = UppercaseTool()

    assert isinstance(tool.description, str)
    assert tool.description.strip() != ""


def test_uppercase_tool_basic_execution():
    tool = UppercaseTool()

    assert tool.execute("hello") == "HELLO"


def test_uppercase_tool_mixed_case():
    tool = UppercaseTool()

    assert tool.execute("Hello World") == "HELLO WORLD"


def test_uppercase_tool_numbers_and_punctuation():
    tool = UppercaseTool()

    assert tool.execute("hello 123!") == "HELLO 123!"


def test_uppercase_tool_already_uppercase():
    tool = UppercaseTool()

    assert tool.execute("HELLO") == "HELLO"


def test_uppercase_tool_preserves_surrounding_whitespace():
    tool = UppercaseTool()

    assert tool.execute("  hello  ") == "  HELLO  "


def test_uppercase_tool_preserves_internal_spacing():
    tool = UppercaseTool()

    assert tool.execute("hello   world") == "HELLO   WORLD"


def test_uppercase_tool_unicode():
    tool = UppercaseTool()

    assert tool.execute("café") == "CAFÉ"


def test_uppercase_tool_is_deterministic():
    tool = UppercaseTool()

    assert tool.execute("same input") == tool.execute("same input")


def test_uppercase_tool_two_executions_are_independent():
    tool = UppercaseTool()

    result1 = tool.execute("hello")
    result2 = tool.execute("world")

    assert result1 == "HELLO"
    assert result2 == "WORLD"


def test_uppercase_tool_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("UppercaseTool must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    tool = UppercaseTool()
    tool.execute("hello")


def test_uppercase_tool_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("UppercaseTool must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    tool = UppercaseTool()
    tool.execute("hello")


def test_uppercase_tool_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    tool = UppercaseTool()

    assert tool.execute("hello") == "HELLO"
