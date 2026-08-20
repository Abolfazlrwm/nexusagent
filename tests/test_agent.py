import pytest

from nexusagent.agent import Agent, AgentResult


def test_agent_result_holds_output_and_success():
    result = AgentResult(output="hello", success=True)

    assert result.output == "hello"
    assert result.success is True


def test_agent_result_is_immutable():
    result = AgentResult(output="hello", success=True)

    with pytest.raises(AttributeError):
        result.output = "changed"


def test_agent_run_returns_agent_result():
    agent = Agent()

    result = agent.run("hello")

    assert isinstance(result, AgentResult)


def test_agent_run_reports_success():
    agent = Agent()

    result = agent.run("hello")

    assert result.success is True


def test_agent_run_returns_expected_placeholder_output():
    agent = Agent()

    result = agent.run("hello")

    assert result.output == "[placeholder] received: hello"


def test_agent_run_raises_on_empty_input():
    agent = Agent()

    with pytest.raises(ValueError):
        agent.run("")


def test_agent_run_raises_on_whitespace_only_input():
    agent = Agent()

    with pytest.raises(ValueError):
        agent.run("   ")


def test_agent_run_does_not_call_external_services(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Agent.run must not perform network calls")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    agent = Agent()
    agent.run("hello")
