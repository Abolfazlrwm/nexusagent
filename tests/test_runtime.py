import pytest

from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
from nexusagent.http_provider import HttpProvider
from nexusagent.provider import Provider
from nexusagent.providers import FakeProvider
from nexusagent.runtime import Runtime, create_runtime
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class EchoProvider(Provider):
    def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"


class FailingProvider(Provider):
    def generate(self, prompt: str) -> str:
        raise RuntimeError("provider failure")


def test_create_runtime_returns_a_runtime():
    runtime = create_runtime()

    assert isinstance(runtime, Runtime)


def test_default_runtime_uses_fake_provider():
    runtime = create_runtime()

    assert isinstance(runtime.agent.provider, FakeProvider)


def test_runtime_run_returns_successful_agent_result():
    runtime = create_runtime()

    result = runtime.run("hello")

    assert isinstance(result, AgentResult)
    assert result.success is True


def test_runtime_run_returns_fake_provider_response():
    runtime = create_runtime()

    result = runtime.run("hello")

    assert result.output == "fake response: hello"


def test_create_runtime_accepts_custom_settings():
    settings = Settings(provider="fake")

    runtime = create_runtime(settings)

    assert isinstance(runtime.agent.provider, FakeProvider)


def test_runtime_wires_settings_into_provider_config():
    settings = Settings(provider="fake", model="fake-model", api_key="secret")

    runtime = create_runtime(settings)

    config = runtime.agent.provider.config
    assert config.model == "fake-model"
    assert config.api_key == "secret"


def test_runtime_wires_endpoint_and_timeout_into_http_provider():
    settings = Settings(
        provider="http",
        endpoint="https://example.test/generate",
        timeout=10,
    )

    runtime = create_runtime(settings)

    assert isinstance(runtime.agent.provider, HttpProvider)
    config = runtime.agent.provider.config
    assert config.endpoint == "https://example.test/generate"
    assert config.timeout == 10


def test_runtime_delegates_to_agent():
    calls = {}

    class RecordingAgent(Agent):
        def run(self, input_text: str) -> AgentResult:
            calls["input_text"] = input_text
            return AgentResult(output="recorded", success=True)

    runtime = Runtime(RecordingAgent(FakeProvider()))
    result = runtime.run("hello")

    assert calls["input_text"] == "hello"
    assert result.output == "recorded"


def test_runtime_execution_uses_the_injected_provider():
    provider = EchoProvider()
    runtime = Runtime(Agent(provider))

    result = runtime.run("hello")

    assert runtime.agent.provider is provider
    assert result.success is True
    assert result.output == "echo: hello"


def test_runtime_run_returns_unsuccessful_result_when_injected_provider_fails():
    runtime = Runtime(Agent(FailingProvider()))

    result = runtime.run("hello")

    assert isinstance(result, AgentResult)
    assert result.success is False
    assert result.output == "provider error: provider failure"


def test_create_runtime_rejects_invalid_configuration():
    settings = Settings(provider="something-unsupported")

    with pytest.raises(ValueError):
        create_runtime(settings)


def test_create_runtime_rejects_http_without_endpoint():
    settings = Settings(provider="http", endpoint=None)

    with pytest.raises(ValueError):
        create_runtime(settings)


def test_create_runtime_accepts_valid_configuration():
    settings = Settings(provider="http", endpoint="https://example.test/generate")

    runtime = create_runtime(settings)

    assert isinstance(runtime, Runtime)


def test_create_runtime_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_runtime() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    settings = Settings(provider="http", endpoint="https://example.test/generate")
    create_runtime(settings)


def test_create_runtime_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_runtime() must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    settings = Settings(provider="http", endpoint="https://example.test/generate")
    create_runtime(settings)


def test_runtime_run_does_not_leak_api_key_on_provider_failure(monkeypatch):
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail)

    settings = Settings(
        provider="http",
        endpoint="https://example.test/generate",
        api_key="super-secret-value",
    )
    runtime = create_runtime(settings)

    result = runtime.run("hello")

    assert result.success is False
    assert "super-secret-value" not in result.output


# --- Tool wiring (Task 1.25) ---


class EchoTool(Tool):
    def execute(self, input_data: str) -> str:
        return input_data


class FailingTool(Tool):
    def execute(self, input_data: str) -> str:
        raise RuntimeError("tool failed")


def make_echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EchoTool(name="echo", description="Echo input"))
    return registry


# Runtime construction


def test_runtime_works_without_tool_dependencies():
    runtime = Runtime(Agent(FakeProvider()))

    assert runtime.tool_registry is None
    assert runtime.tool_executor is None


def test_runtime_accepts_injected_tool_registry():
    registry = ToolRegistry()

    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    assert runtime.tool_registry is registry


def test_runtime_accepts_injected_tool_executor():
    executor = ToolExecutor()

    runtime = Runtime(Agent(FakeProvider()), tool_executor=executor)

    assert runtime.tool_executor is executor


def test_runtime_does_not_create_default_tool_registry():
    runtime = create_runtime()

    assert runtime.tool_registry is None


def test_runtime_does_not_create_default_tool_executor():
    runtime = create_runtime()

    assert runtime.tool_executor is None


def test_create_runtime_preserves_injected_tool_registry_identity():
    registry = make_echo_registry()
    executor = ToolExecutor()

    runtime = create_runtime(Settings(), tool_registry=registry, tool_executor=executor)

    assert runtime.tool_registry is registry
    assert runtime.tool_executor is executor


def test_create_runtime_wires_tools_into_agent():
    registry = make_echo_registry()
    executor = ToolExecutor()

    runtime = create_runtime(Settings(), tool_registry=registry, tool_executor=executor)

    assert runtime.agent.tool_registry is registry
    assert runtime.agent.tool_executor is executor


# Tool execution wiring


def test_runtime_execute_tool_returns_tool_output():
    registry = make_echo_registry()
    runtime = Runtime(
        Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor()),
        tool_registry=registry,
        tool_executor=ToolExecutor(),
    )

    result = runtime.execute_tool("echo", "hello")

    assert result == "hello"


def test_runtime_execute_tool_preserves_exact_input():
    registry = make_echo_registry()
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    result = runtime.execute_tool("echo", "   hello world   ")

    assert result == "   hello world   "


def test_runtime_execute_tool_works_with_second_builtin_tool_without_special_casing():
    from nexusagent.uppercase_tool import UppercaseTool

    registry = ToolRegistry()
    registry.register(UppercaseTool())
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    result = runtime.execute_tool("uppercase", "hello")

    assert result == "HELLO"


def test_runtime_execute_tool_works_with_calculator_builtin_tool():
    from nexusagent.calculator_tool import CalculatorTool

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    result = runtime.execute_tool("calculator", "2 + 3")

    assert result == "5"


def test_runtime_execute_tool_delegates_to_agent_not_registry_or_executor_directly():
    calls = {}

    class RecordingAgent(Agent):
        def execute_tool(self, tool_name: str, input_data: str) -> str:
            calls["tool_name"] = tool_name
            calls["input_data"] = input_data
            return "delegated result"

    runtime = Runtime(RecordingAgent(FakeProvider()))

    result = runtime.execute_tool("echo", "hello")

    assert calls == {"tool_name": "echo", "input_data": "hello"}
    assert result == "delegated result"


def test_runtime_execute_tool_missing_registry_raises_runtime_error():
    runtime = Runtime(Agent(FakeProvider()))

    with pytest.raises(RuntimeError, match="Agent requires a ToolRegistry to execute tools"):
        runtime.execute_tool("echo", "hello")


def test_runtime_execute_tool_missing_executor_raises_runtime_error():
    registry = make_echo_registry()
    runtime = Runtime(Agent(FakeProvider(), tool_registry=registry))

    with pytest.raises(RuntimeError, match="Agent requires a ToolExecutor to execute tools"):
        runtime.execute_tool("echo", "hello")


def test_runtime_execute_tool_propagates_tool_execution_error():
    registry = ToolRegistry()
    registry.register(FailingTool(name="failing", description="Fails"))
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    with pytest.raises(ToolExecutionError):
        runtime.execute_tool("failing", "hello")


def test_runtime_execute_tool_propagates_key_error_for_unknown_tool():
    registry = make_echo_registry()
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    with pytest.raises(KeyError):
        runtime.execute_tool("unknown", "hello")


def test_runtime_execute_tool_propagates_type_error_for_bad_name():
    registry = make_echo_registry()
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    with pytest.raises(TypeError):
        runtime.execute_tool(123, "hello")


def test_runtime_execute_tool_propagates_value_error_for_empty_input():
    registry = make_echo_registry()
    agent = Agent(FakeProvider(), tool_registry=registry, tool_executor=ToolExecutor())
    runtime = Runtime(agent)

    with pytest.raises(ValueError):
        runtime.execute_tool("echo", "")


# Backward compatibility


def test_runtime_agent_still_works_with_tools_injected():
    registry = make_echo_registry()
    runtime = create_runtime(Settings(), tool_registry=registry, tool_executor=ToolExecutor())

    result = runtime.run("hello")

    assert result.output == "fake response: hello"
    assert result.success is True


def test_runtime_run_unaffected_by_tool_injection():
    registry = ToolRegistry()
    registry.register(FailingTool(name="failing", description="Fails"))
    runtime = create_runtime(Settings(), tool_registry=registry, tool_executor=ToolExecutor())

    result = runtime.run("hello")

    assert result.success is True
    assert result.output == "fake response: hello"


# Isolation


def test_two_runtimes_are_independent():
    registry_a = make_echo_registry()
    runtime_a = create_runtime(Settings(), tool_registry=registry_a)
    runtime_b = create_runtime(Settings())

    assert runtime_a.tool_registry is registry_a
    assert runtime_b.tool_registry is None


def test_runtime_construction_does_not_create_global_registry():
    runtime1 = create_runtime()
    runtime2 = create_runtime()

    assert runtime1.tool_registry is None
    assert runtime2.tool_registry is None
    assert runtime1 is not runtime2


# Safety


def test_runtime_construction_with_tools_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Runtime construction must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    registry = make_echo_registry()
    executor = ToolExecutor()
    Runtime(Agent(FakeProvider()), tool_registry=registry, tool_executor=executor)


def test_create_runtime_with_tools_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_runtime() with tools must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    registry = make_echo_registry()
    executor = ToolExecutor()
    create_runtime(Settings(), tool_registry=registry, tool_executor=executor)


def test_create_runtime_with_tools_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_runtime() with tools must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    registry = make_echo_registry()
    executor = ToolExecutor()
    create_runtime(Settings(), tool_registry=registry, tool_executor=executor)


def test_create_runtime_with_tools_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    registry = make_echo_registry()
    executor = ToolExecutor()
    runtime = create_runtime(Settings(), tool_registry=registry, tool_executor=executor)

    result = runtime.execute_tool("echo", "hello")

    assert result == "hello"


# --- Runtime.list_tools() (Task 1.27) ---


def test_runtime_list_tools_returns_registered_tools():
    registry = make_echo_registry()
    runtime = Runtime(Agent(FakeProvider(), tool_registry=registry), tool_registry=registry)

    tools = runtime.list_tools()

    assert [tool.name for tool in tools] == ["echo"]


def test_runtime_list_tools_preserves_registration_order():
    registry = ToolRegistry()
    registry.register(EchoTool(name="a", description="A"))
    registry.register(EchoTool(name="b", description="B"))
    registry.register(EchoTool(name="c", description="C"))
    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    tools = runtime.list_tools()

    assert [tool.name for tool in tools] == ["a", "b", "c"]


def test_runtime_list_tools_empty_registry_returns_empty_list():
    registry = ToolRegistry()
    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    assert runtime.list_tools() == []


def test_runtime_list_tools_without_registry_raises_runtime_error():
    runtime = Runtime(Agent(FakeProvider()))

    with pytest.raises(RuntimeError, match="Runtime requires a ToolRegistry to list tools"):
        runtime.list_tools()


def test_runtime_list_tools_preserves_descriptions():
    registry = ToolRegistry()
    registry.register(EchoTool(name="a", description="Tool A"))
    registry.register(EchoTool(name="b", description="Tool B"))
    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    tools = runtime.list_tools()

    assert [tool.description for tool in tools] == ["Tool A", "Tool B"]


def test_runtime_list_tools_does_not_execute_tools():
    registry = ToolRegistry()
    registry.register(FailingTool(name="failing", description="Fails"))
    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    tools = runtime.list_tools()

    assert [tool.name for tool in tools] == ["failing"]


def test_runtime_list_tools_delegates_to_tool_registry_not_internal_state():
    registry = make_echo_registry()
    runtime = Runtime(Agent(FakeProvider()), tool_registry=registry)

    assert runtime.list_tools() == registry.list_tools()
