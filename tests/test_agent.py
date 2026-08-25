import pytest

from nexusagent.agent import Agent, AgentResult
from nexusagent.providers import FakeProvider


def test_agent_result_holds_output_and_success():
    result = AgentResult(output="hello", success=True)

    assert result.output == "hello"
    assert result.success is True


def test_agent_result_is_immutable():
    result = AgentResult(output="hello", success=True)

    with pytest.raises(AttributeError):
        result.output = "changed"


def test_agent_accepts_a_provider():
    agent = Agent(FakeProvider())

    assert isinstance(agent.provider, FakeProvider)


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
