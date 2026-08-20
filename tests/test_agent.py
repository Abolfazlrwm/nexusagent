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


def test_agent_run_propagates_provider_exception():
    class FailingProvider:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("provider failed")

    agent = Agent(FailingProvider())

    with pytest.raises(RuntimeError):
        agent.run("hello")


def test_agent_run_does_not_call_external_services(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.run must not perform network calls")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    agent = Agent(FakeProvider())
    agent.run("hello")
