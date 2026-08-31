from nexusagent.application import create_application_runtime
from nexusagent.config import Settings
from nexusagent.runtime import Runtime


def test_create_application_runtime_returns_a_runtime():
    runtime = create_application_runtime()

    assert isinstance(runtime, Runtime)


def test_create_application_runtime_tool_listing_order():
    runtime = create_application_runtime()

    names = [tool.name for tool in runtime.list_tools()]

    assert names == ["echo", "uppercase", "calculator"]


def test_create_application_runtime_can_execute_echo():
    runtime = create_application_runtime()

    assert runtime.execute_tool("echo", "hello world") == "hello world"


def test_create_application_runtime_can_execute_uppercase():
    runtime = create_application_runtime()

    assert runtime.execute_tool("uppercase", "hello world") == "HELLO WORLD"


def test_create_application_runtime_can_execute_calculator():
    runtime = create_application_runtime()

    assert runtime.execute_tool("calculator", "2 + 3") == "5"


def test_create_application_runtime_provider_run_still_works():
    runtime = create_application_runtime()

    result = runtime.run("Hello NexusAgent")

    assert result.success is True
    assert result.output == "fake response: Hello NexusAgent"


def test_create_application_runtime_shares_tool_registry_with_agent():
    runtime = create_application_runtime()

    assert runtime.tool_registry is runtime.agent.tool_registry


def test_create_application_runtime_shares_tool_executor_with_agent():
    runtime = create_application_runtime()

    assert runtime.tool_executor is runtime.agent.tool_executor


def test_create_application_runtime_two_calls_produce_independent_runtimes():
    runtime1 = create_application_runtime()
    runtime2 = create_application_runtime()

    assert runtime1 is not runtime2
    assert runtime1.agent is not runtime2.agent


def test_create_application_runtime_two_calls_do_not_share_tool_registry():
    runtime1 = create_application_runtime()
    runtime2 = create_application_runtime()

    assert runtime1.tool_registry is not runtime2.tool_registry


def test_create_application_runtime_two_calls_do_not_share_tool_executor():
    runtime1 = create_application_runtime()
    runtime2 = create_application_runtime()

    assert runtime1.tool_executor is not runtime2.tool_executor


def test_create_application_runtime_two_calls_do_not_share_tool_instances():
    runtime1 = create_application_runtime()
    runtime2 = create_application_runtime()

    assert runtime1.tool_registry.get("echo") is not runtime2.tool_registry.get("echo")


def test_create_application_runtime_propagates_settings_provider(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    settings = Settings(provider="fake")
    runtime = create_application_runtime(settings)

    result = runtime.run("hello")

    assert result.success is True


def test_create_application_runtime_does_not_execute_any_tool(monkeypatch):
    from nexusagent.calculator_tool import CalculatorTool
    from nexusagent.echo_tool import EchoTool
    from nexusagent.uppercase_tool import UppercaseTool

    def fail_if_called(self, input_data):
        raise AssertionError("create_application_runtime() must not execute any tool")

    monkeypatch.setattr(EchoTool, "execute", fail_if_called)
    monkeypatch.setattr(UppercaseTool, "execute", fail_if_called)
    monkeypatch.setattr(CalculatorTool, "execute", fail_if_called)

    create_application_runtime()


def test_create_application_runtime_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_application_runtime() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_application_runtime()


def test_create_application_runtime_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_application_runtime() must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    create_application_runtime()


def test_create_application_runtime_delegates_to_create_tool_runtime(monkeypatch):
    import nexusagent.application as application_module

    calls = []
    sentinel_runtime = object()

    def spy_create_tool_runtime(settings=None):
        calls.append(settings)
        return sentinel_runtime

    monkeypatch.setattr(application_module, "create_tool_runtime", spy_create_tool_runtime)

    settings = Settings(provider="fake")
    result = create_application_runtime(settings)

    assert len(calls) == 1
    assert calls[0] is settings
    assert result is sentinel_runtime


def test_create_application_runtime_delegates_with_default_settings(monkeypatch):
    import nexusagent.application as application_module

    calls = []
    sentinel_runtime = object()

    def spy_create_tool_runtime(settings=None):
        calls.append(settings)
        return sentinel_runtime

    monkeypatch.setattr(application_module, "create_tool_runtime", spy_create_tool_runtime)

    result = create_application_runtime()

    assert calls == [None]
    assert result is sentinel_runtime


def test_create_application_runtime_propagates_custom_model():
    settings = Settings(provider="fake", model="custom-model")

    runtime = create_application_runtime(settings)

    assert runtime.agent.provider.config.model == "custom-model"


def test_create_application_runtime_propagates_custom_api_key_without_leaking():
    settings = Settings(provider="fake", api_key="super-secret-value")

    runtime = create_application_runtime(settings)

    assert runtime.agent.provider.config.api_key == "super-secret-value"
    assert "super-secret-value" not in repr(runtime.agent.provider.config)


def test_create_application_runtime_propagates_custom_log_level_and_env(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    settings = Settings(provider="fake", env="production", log_level="DEBUG")

    runtime = create_application_runtime(settings)

    assert runtime.run("hello").success is True


def test_create_application_runtime_does_not_leak_api_key(monkeypatch, capsys):
    monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

    runtime = create_application_runtime()
    runtime.execute_tool("echo", "hello")

    captured = capsys.readouterr()
    assert "super-secret-value" not in captured.out
    assert "super-secret-value" not in captured.err
    assert "super-secret-value" not in repr(runtime.agent.provider.config)
