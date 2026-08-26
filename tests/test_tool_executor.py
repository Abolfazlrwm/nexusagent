import os

import pytest

from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor


class EchoTool(Tool):
    def execute(self, input_data: str) -> str:
        return input_data


class CountingTool(Tool):
    def __init__(self, name: str = "counter", description: str = "Counts calls"):
        super().__init__(name=name, description=description)
        self.call_count = 0

    def execute(self, input_data: str) -> str:
        self.call_count += 1
        return f"call {self.call_count}: {input_data}"


class FailingTool(Tool):
    def __init__(self, exc: BaseException, name: str = "failing", description: str = "Fails"):
        super().__init__(name=name, description=description)
        self._exc = exc

    def execute(self, input_data: str) -> str:
        raise self._exc


def make_echo_tool() -> EchoTool:
    return EchoTool(name="echo", description="Echo input")


# --- Basic execution ---


def test_execute_returns_tool_output():
    executor = ToolExecutor()
    tool = make_echo_tool()

    result = executor.execute(tool, "hello")

    assert result == "hello"


def test_execute_preserves_surrounding_whitespace_in_output():
    class WhitespaceTool(Tool):
        def execute(self, input_data: str) -> str:
            return "  hello world  "

    executor = ToolExecutor()
    tool = WhitespaceTool(name="ws", description="Whitespace tool")

    result = executor.execute(tool, "hi")

    assert result == "  hello world  "


def test_execute_calls_tool_exactly_once():
    executor = ToolExecutor()
    tool = CountingTool()

    executor.execute(tool, "hello")

    assert tool.call_count == 1


# --- Input validation ---


def test_execute_non_tool_raises_type_error():
    executor = ToolExecutor()

    with pytest.raises(TypeError):
        executor.execute("not a tool", "hello")


def test_execute_non_string_input_raises_type_error():
    executor = ToolExecutor()
    tool = make_echo_tool()

    with pytest.raises(TypeError):
        executor.execute(tool, 123)


def test_execute_empty_input_raises_value_error():
    executor = ToolExecutor()
    tool = make_echo_tool()

    with pytest.raises(ValueError):
        executor.execute(tool, "")


def test_execute_whitespace_only_input_raises_value_error():
    executor = ToolExecutor()
    tool = make_echo_tool()

    with pytest.raises(ValueError):
        executor.execute(tool, "   ")


def test_execute_does_not_call_tool_on_invalid_input():
    executor = ToolExecutor()
    tool = CountingTool()

    with pytest.raises(ValueError):
        executor.execute(tool, "")

    assert tool.call_count == 0


def test_execute_does_not_call_tool_on_non_tool_argument():
    executor = ToolExecutor()

    with pytest.raises(TypeError):
        executor.execute("not a tool", "hello")


# --- Exception handling ---


def test_runtime_error_from_tool_becomes_tool_execution_error():
    executor = ToolExecutor()
    tool = FailingTool(RuntimeError("tool failed"))

    with pytest.raises(ToolExecutionError):
        executor.execute(tool, "hello")


def test_tool_execution_error_preserves_original_message():
    executor = ToolExecutor()
    tool = FailingTool(RuntimeError("tool failed"))

    with pytest.raises(ToolExecutionError, match="tool failed"):
        executor.execute(tool, "hello")


def test_tool_execution_error_cause_is_original_exception():
    executor = ToolExecutor()
    original = RuntimeError("tool failed")
    tool = FailingTool(original)

    with pytest.raises(ToolExecutionError) as exc_info:
        executor.execute(tool, "hello")

    assert exc_info.value.__cause__ is original


@pytest.mark.parametrize("exc_type", [ValueError, TypeError, KeyError, RuntimeError])
def test_various_exception_types_become_tool_execution_error(exc_type):
    executor = ToolExecutor()
    tool = FailingTool(exc_type("boom"))

    with pytest.raises(ToolExecutionError):
        executor.execute(tool, "hello")


def test_keyboard_interrupt_is_not_converted():
    executor = ToolExecutor()
    tool = FailingTool(KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        executor.execute(tool, "hello")


def test_system_exit_is_not_converted():
    executor = ToolExecutor()
    tool = FailingTool(SystemExit())

    with pytest.raises(SystemExit):
        executor.execute(tool, "hello")


def test_tool_execution_error_inherits_from_exception():
    assert issubclass(ToolExecutionError, Exception)


# --- Statelessness ---


def test_two_executions_are_independent():
    executor = ToolExecutor()
    tool = CountingTool()

    result1 = executor.execute(tool, "first")
    result2 = executor.execute(tool, "second")

    assert result1 == "call 1: first"
    assert result2 == "call 2: second"


def test_executor_works_with_different_tools_independently():
    executor = ToolExecutor()
    tool_a = EchoTool(name="a", description="A")
    tool_b = EchoTool(name="b", description="B")

    result_a = executor.execute(tool_a, "hello a")
    result_b = executor.execute(tool_b, "hello b")

    assert result_a == "hello a"
    assert result_b == "hello b"


def test_executor_has_no_internal_state_attributes():
    executor = ToolExecutor()
    tool = make_echo_tool()

    executor.execute(tool, "hello")

    assert not hasattr(executor, "last_tool")
    assert not hasattr(executor, "last_input")
    assert executor.__dict__ == {}


# --- Security ---


def test_tool_execution_error_does_not_leak_api_key():
    executor = ToolExecutor()
    tool = FailingTool(RuntimeError("connection failed"))

    with pytest.raises(ToolExecutionError) as exc_info:
        executor.execute(tool, "hello")

    assert "super-secret-value" not in str(exc_info.value)


def test_executor_does_not_read_nexus_environment_variables(monkeypatch):
    monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

    executor = ToolExecutor()
    tool = make_echo_tool()

    result = executor.execute(tool, "hello")

    assert "super-secret-value" not in result


# --- Network safety ---


def test_executor_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ToolExecutor() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    ToolExecutor()


def test_executor_execute_does_not_perform_network_access_itself(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ToolExecutor.execute() must not perform network access itself")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    executor = ToolExecutor()
    tool = make_echo_tool()
    executor.execute(tool, "hello")


# --- Filesystem safety ---


def test_executor_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ToolExecutor must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    executor = ToolExecutor()
    tool = make_echo_tool()
    executor.execute(tool, "hello")


# --- Environment safety ---


def test_executor_works_without_any_nexus_environment_variables(monkeypatch):
    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    executor = ToolExecutor()
    tool = make_echo_tool()

    result = executor.execute(tool, "hello")

    assert result == "hello"


# --- Dependency isolation ---


def test_tool_executor_module_only_imports_allowed_dependencies():
    import ast

    import nexusagent.tool_executor as executor_module

    with open(executor_module.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)

    forbidden = {
        "nexusagent.agent",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
        "nexusagent.runtime",
        "nexusagent.factory",
        "nexusagent.main",
        "nexusagent.tool_registry",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "http.client",
        "logging",
        "os",
    }

    assert not (set(imports) & forbidden)
    assert set(imports) <= {"__future__", "nexusagent.tool"}
