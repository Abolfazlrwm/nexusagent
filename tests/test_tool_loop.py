"""Tests for the autonomous tool loop in Agent.run()."""

import pytest

from nexusagent.agent import DEFAULT_MAX_ITERATIONS, Agent, AgentResult
from nexusagent.calculator_tool import CalculatorTool
from nexusagent.echo_tool import EchoTool
from nexusagent.provider import (
    Provider,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.providers import ScriptedProvider
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


def make_agent(provider, **kwargs) -> Agent:
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(CalculatorTool())
    return Agent(provider, tool_registry=registry, tool_executor=ToolExecutor(), **kwargs)


# --- the happy path ---


def test_loop_runs_requested_tool_and_returns_final_text():
    provider = ScriptedProvider(
        [ToolCallRequest("calculator", "2 + 3"), TextResponse("The answer is 5")]
    )

    result = make_agent(provider).run("what is 2 + 3?")

    assert result == AgentResult(output="The answer is 5", success=True)


def test_loop_feeds_tool_result_back_to_provider():
    provider = ScriptedProvider([ToolCallRequest("calculator", "6 * 7"), TextResponse("42")])

    make_agent(provider).run("multiply")

    _, _, first_results = provider.calls[0]
    _, _, second_results = provider.calls[1]
    assert first_results == ()
    assert second_results == (ToolResult("calculator", "6 * 7", "42"),)


def test_loop_keeps_original_prompt_on_every_call():
    provider = ScriptedProvider([ToolCallRequest("echo", "x"), TextResponse("done")])

    make_agent(provider).run("original question")

    assert [call[0] for call in provider.calls] == ["original question"] * 2


def test_loop_supports_several_sequential_tool_calls_in_order():
    provider = ScriptedProvider(
        [
            ToolCallRequest("calculator", "1 + 1"),
            ToolCallRequest("echo", "hello"),
            ToolCallRequest("calculator", "10 / 4"),
            TextResponse("all done"),
        ]
    )

    result = make_agent(provider).run("do things")

    assert result.output == "all done"
    assert provider.calls[-1][2] == (
        ToolResult("calculator", "1 + 1", "2"),
        ToolResult("echo", "hello", "hello"),
        ToolResult("calculator", "10 / 4", "2.5"),
    )


def test_loop_advertises_registered_tools_to_provider():
    provider = ScriptedProvider([TextResponse("hi")])

    make_agent(provider).run("hello")

    _, tools, _ = provider.calls[0]
    assert tools == (
        ToolSpec("echo", "Returns its input unchanged."),
        ToolSpec("calculator", "Performs basic arithmetic operations."),
    )


def test_agent_without_tools_advertises_nothing():
    provider = ScriptedProvider([TextResponse("hi")])

    Agent(provider).run("hello")

    assert provider.calls[0][1] == ()


# --- tool failures are recoverable ---


@pytest.mark.parametrize(
    ("request_", "expected_fragment"),
    [
        (ToolCallRequest("missing", "x"), "not registered"),
        (ToolCallRequest("calculator", "1 / 0"), "Division by zero"),
        (ToolCallRequest("calculator", "banana"), "Invalid expression"),
        (ToolCallRequest("echo", "   "), "must not be empty"),
    ],
)
def test_tool_failure_is_fed_back_as_error_result_and_run_continues(request_, expected_fragment):
    provider = ScriptedProvider([request_, TextResponse("recovered")])

    result = make_agent(provider).run("try it")

    assert result == AgentResult(output="recovered", success=True)
    (fed_back,) = provider.calls[1][2]
    assert fed_back.is_error is True
    assert expected_fragment in fed_back.output


def test_provider_can_retry_after_a_tool_error():
    provider = ScriptedProvider(
        [
            ToolCallRequest("calculator", "two plus two"),
            ToolCallRequest("calculator", "2 + 2"),
            TextResponse("4"),
        ]
    )

    result = make_agent(provider).run("add")

    assert result.output == "4"
    results = provider.calls[2][2]
    assert [r.is_error for r in results] == [True, False]


# --- limits and failure modes ---


def test_iteration_limit_stops_a_runaway_provider():
    provider = ScriptedProvider([ToolCallRequest("echo", "again")] * 50)

    result = make_agent(provider, max_iterations=3).run("loop forever")

    assert result.success is False
    assert "maximum of 3 iterations" in result.output
    assert len(provider.calls) == 3


def test_run_finishing_exactly_on_the_last_iteration_succeeds():
    provider = ScriptedProvider([ToolCallRequest("echo", "x"), TextResponse("ok")])

    result = make_agent(provider, max_iterations=2).run("hi")

    assert result == AgentResult(output="ok", success=True)


def test_default_max_iterations_is_applied():
    provider = ScriptedProvider([ToolCallRequest("echo", "x")] * 100)

    result = make_agent(provider).run("hi")

    assert result.success is False
    assert len(provider.calls) == DEFAULT_MAX_ITERATIONS


def test_provider_error_mid_loop_becomes_failed_result():
    provider = ScriptedProvider([ToolCallRequest("echo", "x")])  # script runs out

    result = make_agent(provider).run("hi")

    assert result.success is False
    assert result.output.startswith("provider error:")


def test_tool_call_without_tools_configured_fails_cleanly():
    provider = ScriptedProvider([ToolCallRequest("echo", "x")])

    result = Agent(provider).run("hi")

    assert result.success is False
    assert "no tools configured" in result.output
    assert len(provider.calls) == 1


def test_tool_call_with_registry_but_no_executor_fails_cleanly():
    provider = ScriptedProvider([ToolCallRequest("echo", "x")])

    result = Agent(provider, tool_registry=ToolRegistry()).run("hi")

    assert result.success is False
    assert "no tools configured" in result.output


def test_unexpected_response_type_fails_cleanly():
    class WeirdProvider(Provider):
        def generate(self, prompt):
            return "unused"

        def generate_response(self, prompt, *, tools=(), tool_results=()):
            return 42

    result = make_agent(WeirdProvider()).run("hi")

    assert result.success is False
    assert "unexpected response type" in result.output


def test_keyboard_interrupt_is_not_swallowed_by_the_loop():
    class Interrupting(Provider):
        def generate(self, prompt):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        make_agent(Interrupting()).run("hi")


def test_each_run_starts_with_a_clean_tool_history():
    provider = ScriptedProvider(
        [
            ToolCallRequest("echo", "a"),
            TextResponse("first"),
            TextResponse("second"),
        ]
    )
    agent = make_agent(provider)

    agent.run("one")
    agent.run("two")

    assert provider.calls[2][2] == ()


# --- constructor validation ---


@pytest.mark.parametrize("bad", [0, -1])
def test_max_iterations_must_be_positive(bad):
    with pytest.raises(ValueError):
        Agent(ScriptedProvider([]), max_iterations=bad)


@pytest.mark.parametrize("bad", [1.5, "3", None, True])
def test_max_iterations_must_be_an_int(bad):
    with pytest.raises(TypeError):
        Agent(ScriptedProvider([]), max_iterations=bad)


# --- ScriptedProvider itself ---


def test_scripted_provider_generate_returns_text():
    assert ScriptedProvider([TextResponse("hi")]).generate("x") == "hi"


def test_scripted_provider_generate_rejects_tool_call():
    with pytest.raises(ProviderResponseError):
        ScriptedProvider([ToolCallRequest("echo", "x")]).generate("x")


def test_scripted_provider_raises_when_script_is_exhausted():
    provider = ScriptedProvider([TextResponse("only one")])
    provider.generate("x")

    with pytest.raises(ProviderResponseError):
        provider.generate("x")


# --- default Provider.generate_response ---


def test_default_generate_response_wraps_generate_as_text():
    class Plain(Provider):
        def generate(self, prompt):
            return f"plain: {prompt}"

    assert Plain().generate_response("hi") == TextResponse("plain: hi")


def test_text_only_provider_works_with_a_tool_equipped_agent():
    class Plain(Provider):
        def generate(self, prompt):
            return "just text"

    result = make_agent(Plain()).run("hi")

    assert result == AgentResult(output="just text", success=True)
