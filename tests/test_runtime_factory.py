from nexusagent.runtime import Runtime
from nexusagent.runtime_factory import create_tool_runtime


def test_create_tool_runtime_returns_a_runtime():
    runtime = create_tool_runtime()

    assert isinstance(runtime, Runtime)


def test_create_tool_runtime_configures_expected_tool_names():
    runtime = create_tool_runtime()

    names = [tool.name for tool in runtime.list_tools()]

    assert names == ["echo", "uppercase", "calculator"]


def test_create_tool_runtime_configures_expected_descriptions():
    runtime = create_tool_runtime()

    tools = {tool.name: tool.description for tool in runtime.list_tools()}

    assert tools == {
        "echo": "Returns its input unchanged.",
        "uppercase": "Converts input to uppercase.",
        "calculator": "Performs basic arithmetic operations.",
    }


def test_create_tool_runtime_can_execute_echo():
    runtime = create_tool_runtime()

    result = runtime.execute_tool("echo", "hello world")

    assert result == "hello world"


def test_create_tool_runtime_can_execute_uppercase():
    runtime = create_tool_runtime()

    result = runtime.execute_tool("uppercase", "hello world")

    assert result == "HELLO WORLD"


def test_create_tool_runtime_can_execute_calculator():
    runtime = create_tool_runtime()

    result = runtime.execute_tool("calculator", "2 + 3")

    assert result == "5"


def test_create_tool_runtime_list_tools_preserves_registration_order():
    runtime = create_tool_runtime()

    tools = runtime.list_tools()

    assert [tool.name for tool in tools] == ["echo", "uppercase", "calculator"]


def test_create_tool_runtime_agent_and_runtime_share_same_tool_registry():
    runtime = create_tool_runtime()

    assert runtime.tool_registry is runtime.agent.tool_registry


def test_create_tool_runtime_agent_and_runtime_share_same_tool_executor():
    runtime = create_tool_runtime()

    assert runtime.tool_executor is runtime.agent.tool_executor


def test_create_tool_runtime_two_calls_produce_independent_runtimes():
    runtime1 = create_tool_runtime()
    runtime2 = create_tool_runtime()

    assert runtime1 is not runtime2


def test_create_tool_runtime_two_calls_do_not_share_tool_registry():
    runtime1 = create_tool_runtime()
    runtime2 = create_tool_runtime()

    assert runtime1.tool_registry is not runtime2.tool_registry


def test_create_tool_runtime_two_calls_do_not_share_tool_executor():
    runtime1 = create_tool_runtime()
    runtime2 = create_tool_runtime()

    assert runtime1.tool_executor is not runtime2.tool_executor


def test_create_tool_runtime_two_calls_do_not_share_tool_instances():
    runtime1 = create_tool_runtime()
    runtime2 = create_tool_runtime()

    assert runtime1.tool_registry.get("echo") is not runtime2.tool_registry.get("echo")


def test_create_tool_runtime_does_not_execute_any_tool(monkeypatch):
    from nexusagent.calculator_tool import CalculatorTool
    from nexusagent.echo_tool import EchoTool
    from nexusagent.uppercase_tool import UppercaseTool

    def fail_if_called(self, input_data):
        raise AssertionError("create_tool_runtime() must not execute any tool")

    monkeypatch.setattr(EchoTool, "execute", fail_if_called)
    monkeypatch.setattr(UppercaseTool, "execute", fail_if_called)
    monkeypatch.setattr(CalculatorTool, "execute", fail_if_called)

    create_tool_runtime()


def test_create_tool_runtime_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_tool_runtime() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_tool_runtime()


def test_create_tool_runtime_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_tool_runtime() must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    create_tool_runtime()


def test_create_tool_runtime_does_not_leak_api_key(monkeypatch, capsys):
    monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

    runtime = create_tool_runtime()
    runtime.execute_tool("echo", "hello")

    captured = capsys.readouterr()
    assert "super-secret-value" not in captured.out
    assert "super-secret-value" not in captured.err
    assert "super-secret-value" not in repr(runtime.agent.provider.config)
