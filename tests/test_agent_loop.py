import pytest

from nexusagent.agent import Agent, AgentStep, Conversation
from nexusagent.provider import Message, TextResponse, ToolCallRequest, ToolSpec
from nexusagent.providers import ScriptedProvider
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_factory import create_tool_registry


def make_agent(responses, **kwargs):
    provider = ScriptedProvider(responses)
    agent = Agent(
        provider, tool_registry=create_tool_registry(), tool_executor=ToolExecutor(), **kwargs
    )
    return agent, provider


def test_text_response_ends_the_loop_immediately():
    agent, provider = make_agent(["done"])

    result = agent.run("hi")

    assert result.success is True
    assert result.output == "done"
    assert result.steps == ()
    assert len(provider.calls) == 1


def test_tool_call_is_executed_and_result_fed_back():
    agent, provider = make_agent([ToolCallRequest("calculator", "2 + 3"), "The answer is 5"])

    result = agent.run("what is 2 + 3?")

    assert result.success is True
    assert result.output == "The answer is 5"
    assert result.steps == (AgentStep("calculator", "2 + 3", "5"),)
    second_call_messages, _ = provider.calls[1]
    assert second_call_messages[-1].role == "tool"
    assert second_call_messages[-1].content == "5"
    assert second_call_messages[-2].role == "assistant"
    assert second_call_messages[-2].tool_call.tool_name == "calculator"


def test_provider_is_told_which_tools_exist():
    agent, provider = make_agent(["ok"])

    agent.run("hi")

    _, tools = provider.calls[0]
    assert {t.name for t in tools} == {"echo", "uppercase", "calculator"}
    assert all(isinstance(t, ToolSpec) for t in tools)


def test_missing_call_id_is_assigned():
    agent, provider = make_agent([ToolCallRequest("echo", "x"), "ok"])

    agent.run("hi")

    messages, _ = provider.calls[1]
    assert messages[-1].tool_call.call_id == "call_1"
    assert messages[-2].tool_call.call_id == "call_1"


def test_backend_call_id_is_preserved():
    agent, provider = make_agent([ToolCallRequest("echo", "x", call_id="abc"), "ok"])

    agent.run("hi")

    assert provider.calls[1][0][-1].tool_call.call_id == "abc"


def test_multiple_sequential_tool_calls():
    agent, _ = make_agent(
        [ToolCallRequest("calculator", "2 + 3"), ToolCallRequest("uppercase", "five"), "done"]
    )

    result = agent.run("go")

    assert [s.tool_name for s in result.steps] == ["calculator", "uppercase"]
    assert result.steps[1].tool_output == "FIVE"


@pytest.mark.parametrize(
    "request_",
    [
        ToolCallRequest("nope", "x"),
        ToolCallRequest("calculator", "hello"),
        ToolCallRequest("calculator", "10 / 0"),
        ToolCallRequest("echo", "   "),
    ],
)
def test_tool_errors_are_reported_to_the_model_not_raised(request_):
    agent, provider = make_agent([request_, "recovered"])

    result = agent.run("go")

    assert result.success is True
    assert result.output == "recovered"
    assert result.steps[0].is_error is True
    assert provider.calls[1][0][-1].content.startswith("error:")


def test_max_steps_stops_a_runaway_loop():
    agent, _ = make_agent([ToolCallRequest("echo", "x")] * 10, max_steps=3)

    result = agent.run("go")

    assert result.success is False
    assert "3 steps" in result.output
    assert len(result.steps) == 3


def test_tool_request_without_tools_configured_fails_cleanly():
    agent = Agent(ScriptedProvider([ToolCallRequest("echo", "x")]))

    result = agent.run("go")

    assert result.success is False
    assert "no tools configured" in result.output


def test_provider_failure_mid_loop_returns_unsuccessful_result():
    agent, _ = make_agent([ToolCallRequest("echo", "x")])  # script runs out on 2nd call

    result = agent.run("go")

    assert result.success is False
    assert result.output.startswith("provider error:")
    assert len(result.steps) == 1


def test_unsupported_response_type_fails_cleanly():
    class Weird:
        def respond(self, messages, tools=()):
            return 42

    result = Agent(Weird()).run("go")

    assert result.success is False
    assert "unsupported response type" in result.output


def test_system_prompt_is_first_message_and_not_stored_in_result():
    agent, provider = make_agent(["ok"], system_prompt="Be brief.")

    result = agent.run("hi")

    assert provider.calls[0][0][0] == Message("system", "Be brief.")
    assert all(m.role != "system" for m in result.messages)


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_max_steps_value(bad):
    with pytest.raises(ValueError):
        Agent(ScriptedProvider([]), max_steps=bad)


@pytest.mark.parametrize("bad", ["3", 1.5, True, None])
def test_invalid_max_steps_type(bad):
    with pytest.raises(TypeError):
        Agent(ScriptedProvider([]), max_steps=bad)


def test_blank_system_prompt_rejected():
    with pytest.raises(ValueError):
        Agent(ScriptedProvider([]), system_prompt="  ")


def test_generate_only_provider_still_works_with_tools_configured():
    class Legacy:
        def generate(self, prompt):
            return f"legacy: {prompt}"

    agent = Agent(Legacy(), tool_registry=create_tool_registry(), tool_executor=ToolExecutor())

    assert agent.run("hi").output == "legacy: hi"


# --- Conversation ---


def test_conversation_carries_history_between_turns():
    provider = ScriptedProvider(["first answer", "second answer"])
    conv = Conversation(Agent(provider))

    conv.send("one")
    conv.send("two")

    second_call_messages, _ = provider.calls[1]
    assert [(m.role, m.content) for m in second_call_messages] == [
        ("user", "one"),
        ("assistant", "first answer"),
        ("user", "two"),
    ]
    assert len(conv.messages) == 4


def test_conversation_discards_failed_turns():
    provider = ScriptedProvider(["ok"])  # second turn fails: script exhausted
    conv = Conversation(Agent(provider))

    conv.send("one")
    failed = conv.send("two")

    assert failed.success is False
    assert [m.content for m in conv.messages] == ["one", "ok"]


def test_conversation_reset_clears_history():
    conv = Conversation(Agent(ScriptedProvider(["a"])))
    conv.send("x")

    conv.reset()

    assert conv.messages == ()


def test_conversation_keeps_tool_turns_in_history():
    provider = ScriptedProvider([ToolCallRequest("echo", "hey"), "done", "again"])
    agent = Agent(provider, tool_registry=create_tool_registry(), tool_executor=ToolExecutor())
    conv = Conversation(agent)

    conv.send("one")
    conv.send("two")

    roles = [m.role for m in provider.calls[2][0]]
    assert roles == ["user", "assistant", "tool", "assistant", "user"]


def test_scripted_provider_generate_returns_text():
    assert ScriptedProvider(["hi"]).generate("x") == "hi"
    assert isinstance(ScriptedProvider(["hi"]).respond([Message("user", "x")]), TextResponse)
