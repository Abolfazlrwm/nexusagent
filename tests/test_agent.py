import pytest

from nexusagent.agent import Agent, AgentResult
from nexusagent.providers import FakeProvider
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry


def test_agent_result_holds_output_and_success():
    result = AgentResult(output="hello", success=True)

    assert result.output == "hello"
    assert result.success is True


def test_agent_result_has_exactly_output_and_success_fields():
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(AgentResult)}

    assert field_names == {"output", "success"}


def test_agent_result_is_immutable():
    result = AgentResult(output="hello", success=True)

    with pytest.raises(AttributeError):
        result.output = "changed"


def test_agent_accepts_a_provider():
    agent = Agent(FakeProvider())

    assert isinstance(agent.provider, FakeProvider)


def test_agent_run_uses_the_configured_fake_provider():
    provider = FakeProvider()
    agent = Agent(provider)

    result = agent.run("hello")

    assert agent.provider is provider
    assert result.output == "fake response: hello"
    assert result.success is True


def test_agent_run_returns_agent_result():
    agent = Agent(FakeProvider())

    result = agent.run("hello")

    assert isinstance(result, AgentResult)


def test_agent_run_reports_success():
    agent = Agent(FakeProvider())

    result = agent.run("hello")

    assert result.success is True


def test_agent_run_passes_input_to_provider():
    received = {}

    class RecordingProvider:
        def generate(self, prompt: str) -> str:
            received["prompt"] = prompt
            return "response"

    agent = Agent(RecordingProvider())
    agent.run("hello")

    assert received["prompt"] == "hello"


def test_agent_run_output_comes_from_provider():
    agent = Agent(FakeProvider())

    result = agent.run("hello")

    assert result.output == "fake response: hello"


def test_agent_run_raises_on_empty_input():
    agent = Agent(FakeProvider())

    with pytest.raises(ValueError):
        agent.run("")


def test_agent_run_raises_on_whitespace_only_input():
    agent = Agent(FakeProvider())

    with pytest.raises(ValueError):
        agent.run("   ")


@pytest.mark.parametrize("invalid_input", [None, 123, 3.14, ["hello"], {"text": "hello"}])
def test_agent_run_raises_type_error_on_non_string_input(invalid_input):
    agent = Agent(FakeProvider())

    with pytest.raises(TypeError, match="input_text must be a string"):
        agent.run(invalid_input)


def test_agent_run_returns_unsuccessful_result_on_provider_failure():
    class FailingProvider:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("provider failed")

    agent = Agent(FailingProvider())

    result = agent.run("hello")

    assert isinstance(result, AgentResult)
    assert result.success is False


def test_agent_run_provider_failure_message_in_output():
    class FailingProvider:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("provider failed")

    agent = Agent(FailingProvider())

    result = agent.run("hello")

    assert result.output == "provider error: provider failed"


def test_agent_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent construction must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    Agent(FakeProvider())


def test_agent_run_calls_provider_exactly_once():
    class CountingProvider:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            return "response"

    provider = CountingProvider()
    agent = Agent(provider)
    agent.run("hello")

    assert provider.call_count == 1


def test_agent_run_does_not_call_provider_on_non_string_input():
    class CountingProvider:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            return "response"

    provider = CountingProvider()
    agent = Agent(provider)

    with pytest.raises(TypeError):
        agent.run(123)

    assert provider.call_count == 0


def test_agent_run_does_not_call_provider_on_empty_input():
    class CountingProvider:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            return "response"

    provider = CountingProvider()
    agent = Agent(provider)

    with pytest.raises(ValueError):
        agent.run("")

    assert provider.call_count == 0


def test_agent_run_does_not_call_provider_on_whitespace_only_input():
    class CountingProvider:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            return "response"

    provider = CountingProvider()
    agent = Agent(provider)

    with pytest.raises(ValueError):
        agent.run("   ")

    assert provider.call_count == 0


def test_agent_run_preserves_surrounding_whitespace_in_successful_output():
    class WhitespaceProvider:
        def generate(self, prompt: str) -> str:
            return " hello "

    agent = Agent(WhitespaceProvider())
    result = agent.run("hi")

    assert result.output == " hello "


def test_agent_run_two_sequential_calls_are_independent():
    class EchoProvider:
        def __init__(self):
            self.call_count = 0

        def generate(self, prompt: str) -> str:
            self.call_count += 1
            return f"echo: {prompt}"

    provider = EchoProvider()
    agent = Agent(provider)

    result1 = agent.run("first")
    result2 = agent.run("second")

    assert result1.output == "echo: first"
    assert result2.output == "echo: second"
    assert provider.call_count == 2


def test_agent_run_second_call_unaffected_by_first_failure():
    class FlakyProvider:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("first call fails")
            return f"ok: {prompt}"

    provider = FlakyProvider()
    agent = Agent(provider)

    result1 = agent.run("first")
    result2 = agent.run("second")

    assert result1.success is False
    assert result2.success is True
    assert result2.output == "ok: second"


def test_agent_run_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.run must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    agent = Agent(FakeProvider())
    agent.run("hello")


def test_agent_run_does_not_call_external_services(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.run must not perform network calls")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    agent = Agent(FakeProvider())
    agent.run("hello")


# --- Tool support (Task 1.24) ---


class EchoTool(Tool):
    def execute(self, input_data: str) -> str:
        return input_data


class FailingTool(Tool):
    def execute(self, input_data: str) -> str:
        raise RuntimeError("tool failed")


def make_echo_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EchoTool(name="echo", description="Echo input"))
    return registry


class RecordingRegistry:
    def __init__(self, tool):
        self.tool = tool
        self.requested_name = None

    def get(self, name):
        self.requested_name = name
        return self.tool


class RecordingExecutor:
    def __init__(self, result):
        self.result = result
        self.received_tool = None
        self.received_input = None

    def execute(self, tool, input_data):
        self.received_tool = tool
        self.received_input = input_data
        return self.result


class ExplodingRegistry:
    def get(self, name):
        raise AssertionError("registry.get must not be called by Agent.run()")


class ExplodingExecutor:
    def execute(self, tool, input_data):
        raise AssertionError("executor.execute must not be called by Agent.run()")


# A. Backward compatibility


def test_agent_still_works_without_tool_dependencies():
    agent = Agent(FakeProvider())

    result = agent.run("hello")

    assert result.output == "fake response: hello"
    assert result.success is True


# B. Constructor dependency injection


def test_agent_stores_injected_tool_registry_and_executor():
    registry = ToolRegistry()
    executor = ToolExecutor()

    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=executor)

    assert agent.tool_registry is registry
    assert agent.tool_executor is executor


# C. Successful tool execution


def test_agent_execute_tool_returns_tool_output():
    agent = Agent(
        FakeProvider(),
        tool_registry=make_echo_tool_registry(),
        tool_executor=ToolExecutor(),
    )

    result = agent.execute_tool("echo", "hello")

    assert result == "hello"


# D. Correct registry lookup


def test_agent_execute_tool_passes_tool_name_to_registry():
    tool = EchoTool(name="echo", description="Echo input")
    registry = RecordingRegistry(tool)
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())

    agent.execute_tool("echo", "hello")

    assert registry.requested_name == "echo"


# E. Correct executor usage


def test_agent_execute_tool_passes_resolved_tool_to_executor():
    tool = EchoTool(name="echo", description="Echo input")
    registry = RecordingRegistry(tool)
    executor = RecordingExecutor(result="response")
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=executor)

    agent.execute_tool("echo", "hello")

    assert executor.received_tool is tool


# F. Exact input preservation


def test_agent_execute_tool_passes_input_unchanged():
    tool = EchoTool(name="echo", description="Echo input")
    registry = RecordingRegistry(tool)
    executor = RecordingExecutor(result="response")
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=executor)

    agent.execute_tool("echo", "   hello world   ")

    assert executor.received_input == "   hello world   "


# G. Result preservation


def test_agent_execute_tool_returns_executor_result_unchanged():
    tool = EchoTool(name="echo", description="Echo input")
    registry = RecordingRegistry(tool)
    executor = RecordingExecutor(result="  result  ")
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=executor)

    result = agent.execute_tool("echo", "hello")

    assert result == "  result  "


# H. Missing registry


def test_agent_execute_tool_without_registry_raises_runtime_error():
    agent = Agent(FakeProvider())

    with pytest.raises(RuntimeError, match="Agent requires a ToolRegistry to execute tools"):
        agent.execute_tool("echo", "hello")


# I. Missing executor


def test_agent_execute_tool_without_executor_raises_runtime_error():
    agent = Agent(FakeProvider(), tool_registry=make_echo_tool_registry())

    with pytest.raises(RuntimeError, match="Agent requires a ToolExecutor to execute tools"):
        agent.execute_tool("echo", "hello")


# J. Registry errors propagate unchanged


def test_agent_execute_tool_propagates_registry_type_error():
    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )

    with pytest.raises(TypeError):
        agent.execute_tool(123, "hello")


def test_agent_execute_tool_propagates_registry_value_error():
    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )

    with pytest.raises(ValueError):
        agent.execute_tool("", "hello")


def test_agent_execute_tool_propagates_registry_key_error():
    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )

    with pytest.raises(KeyError):
        agent.execute_tool("unknown", "hello")


# K. Executor errors propagate unchanged


def test_agent_execute_tool_propagates_tool_execution_error():
    registry = ToolRegistry()
    registry.register(FailingTool(name="failing", description="Fails"))
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())

    with pytest.raises(ToolExecutionError):
        agent.execute_tool("failing", "hello")


# L. Tool.execute() is not called directly by Agent


def test_agent_execute_tool_goes_through_executor_not_directly():
    tool = EchoTool(name="echo", description="Echo input")
    registry = RecordingRegistry(tool)
    executor = RecordingExecutor(result="via executor")
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=executor)

    result = agent.execute_tool("echo", "hello")

    assert result == "via executor"
    assert executor.received_tool is tool


# M. Agent.run() regression - must not touch tool infrastructure


def test_agent_run_does_not_use_tool_registry_or_executor():
    agent = Agent(
        FakeProvider(), tool_registry=ExplodingRegistry(), tool_executor=ExplodingExecutor()
    )

    result = agent.run("hello")

    assert result.output == "fake response: hello"


# N. Statelessness of execute_tool


def test_agent_execute_tool_two_calls_are_independent():
    registry = ToolRegistry()
    registry.register(EchoTool(name="echo", description="Echo input"))
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())

    result1 = agent.execute_tool("echo", "first")
    result2 = agent.execute_tool("echo", "second")

    assert result1 == "first"
    assert result2 == "second"


# O. Network safety


def test_agent_execute_tool_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.execute_tool must not perform network access itself")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )
    agent.execute_tool("echo", "hello")


# P. Filesystem safety


def test_agent_execute_tool_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.execute_tool must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )
    agent.execute_tool("echo", "hello")


# Q. Environment safety


def test_agent_execute_tool_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    agent = Agent(
        FakeProvider(), tool_registry=make_echo_tool_registry(), tool_executor=ToolExecutor()
    )

    result = agent.execute_tool("echo", "hello")

    assert result == "hello"
