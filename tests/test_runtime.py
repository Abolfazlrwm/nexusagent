from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
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
