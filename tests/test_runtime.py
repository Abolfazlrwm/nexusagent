import pytest

from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
from nexusagent.http_provider import HttpProvider
from nexusagent.providers import FakeProvider
from nexusagent.runtime import Runtime, create_runtime


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
