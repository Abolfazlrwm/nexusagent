"""Offline demo brain (ADR 0016): the DemoProvider contract and behavior.

DemoProvider is deterministic by contract — every test below asserts a
byte-stable answer, the tool-loop integration runs the real Agent with
the real calculator tool, and the name-memory integration runs two
Agent.run() calls across a real InMemoryMemory.
"""

from __future__ import annotations

import pytest

from nexusagent import DemoProvider, ToolExecutor
from nexusagent.agent import Agent
from nexusagent.demo_provider import _FALLBACK_REPLY
from nexusagent.memory import InMemoryMemory
from nexusagent.provider import (
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.tool_factory import create_tool_registry


@pytest.fixture()
def provider() -> DemoProvider:
    return DemoProvider()


# -- the fact sheet ------------------------------------------------------


def test_the_sky_question_gets_a_real_answer(provider: DemoProvider):
    response = provider.generate_response("what color is sky")

    assert isinstance(response, TextResponse)
    assert "Blue" in response.text
    assert "Rayleigh scattering" in response.text


@pytest.mark.parametrize(
    "prompt",
    [
        "what color is the sky?",
        "What color is the sky",
        "what's the color of the sky?",
        "what colour is the sky",
    ],
)
def test_sky_question_phrasings_all_answer_blue(provider: DemoProvider, prompt: str):
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert "Blue" in response.text


@pytest.mark.parametrize(
    "prompt",
    ["what color is a banana?", "what color is an apple?".replace("apple", "banana")],
)
def test_articles_are_stripped_before_lookup(provider: DemoProvider, prompt: str):
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert "Yellow" in response.text


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("what color is the sun?", "White"),
        ("what color is grass?", "Green"),
        ("what color is a leaf?", "Green"),
        ("what color is blood?", "Red"),
        ("what color is snow?", "White"),
        ("what color is a rose?", "red"),
    ],
)
def test_fact_sheet_entries(provider: DemoProvider, prompt: str, expected: str):
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert expected in response.text


def test_unknown_noun_gets_an_honest_offline_answer(provider: DemoProvider):
    response = provider.generate_response("what color is a quasar?")

    assert isinstance(response, TextResponse)
    assert "quasar" in response.text
    assert "no API keys" in response.text or "no network" in response.text


def test_fact_sheet_noun_matching_is_case_and_space_insensitive(provider: DemoProvider):
    response = provider.generate_response("What Color Is THE  Sky?")

    assert isinstance(response, TextResponse)
    assert "Blue" in response.text


# -- the honest fallback -------------------------------------------------


def test_open_ended_questions_fall_back_honestly(provider: DemoProvider):
    response = provider.generate_response("explain quantum entanglement")

    assert isinstance(response, TextResponse)
    assert response.text == _FALLBACK_REPLY
    assert "DemoProvider" in response.text


def test_fallback_names_the_built_in_real_providers(provider: DemoProvider):
    response = provider.generate_response("write me a poem")

    assert isinstance(response, TextResponse)
    assert "OpenAI" in response.text and "Anthropic" in response.text and "Gemini" in response.text


# -- small talk -----------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("hello", "Hello"),
        ("hi", "Hello"),
        ("hey there", "Hello"),
        ("who are you", "DemoProvider"),
        ("what can you do?", "calculator"),
        ("how are you?", "Deterministic"),
        ("thank you", "welcome"),
        ("bye", "Goodbye"),
        ("tell me a joke", "step budget"),
    ],
)
def test_small_talk_answers(provider: DemoProvider, prompt: str, expected: str):
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert expected in response.text


# -- math through the real tool loop -------------------------------------


def test_math_with_calculator_tool_requests_the_tool(provider: DemoProvider):
    response = provider.generate_response(
        "what is 144 / 12", tools=(ToolSpec("calculator", "arithmetic"),)
    )

    assert isinstance(response, ToolCallRequest)
    assert response.tool_name == "calculator"
    assert response.tool_input == "144 / 12"


def test_bare_expression_with_calculator_requests_the_full_text(provider: DemoProvider):
    response = provider.generate_response("2+2*3", tools=(ToolSpec("calculator", "math"),))

    assert isinstance(response, ToolCallRequest)
    assert response.tool_input == "2+2*3"


def test_math_without_calculator_explains_what_is_missing(provider: DemoProvider):
    response = provider.generate_response("what is 144 / 12")

    assert isinstance(response, TextResponse)
    assert "calculator" in response.text


def test_calculator_result_is_phrased_into_the_answer(provider: DemoProvider):
    result = ToolResult("calculator", "144 / 12", "12")
    response = provider.generate_response("what is 144 / 12", tool_results=(result,))

    assert isinstance(response, TextResponse)
    assert response.text == "144 / 12 equals 12."


def test_generic_tool_result_is_phrased_neutrally(provider: DemoProvider):
    result = ToolResult("echo", "hi", "hi")
    response = provider.generate_response("echo hi", tool_results=(result,))

    assert isinstance(response, TextResponse)
    assert response.text == "The echo tool returned hi."


def test_failed_tool_result_reports_the_error(provider: DemoProvider):
    result = ToolResult("calculator", "1/0", "division by zero", is_error=True)
    response = provider.generate_response("1/0", tool_results=(result,))

    assert isinstance(response, TextResponse)
    assert "failed" in response.text


def test_math_inside_composed_prompt_uses_the_math_span(provider: DemoProvider):
    composed = "transcript:\nuser: earlier text\n\nNew message:\nwhat is 6 * 7?"
    response = provider.generate_response(composed, tools=(ToolSpec("calculator", "math"),))

    assert isinstance(response, ToolCallRequest)
    assert response.tool_input == "6 * 7"


# -- name memory across runs (real Agent + real memory) -------------------


def test_name_is_remembered_across_two_agent_runs():
    memory = InMemoryMemory()
    agent = Agent(DemoProvider(), memory=memory)

    first = agent.run("my name is Sara")
    second = agent.run("what is my name?")

    assert first.success and "Sara" in first.output
    assert second.success and "Sara" in second.output
    assert "earlier run" in second.output


def test_who_am_i_without_memory_is_honest(provider: DemoProvider):
    response = provider.generate_response("what is my name?")

    assert isinstance(response, TextResponse)
    assert "don't know" in response.text


def test_most_recent_name_wins(provider: DemoProvider):
    prompt = (
        "transcript:\nuser: my name is Dara\nassistant: hi Dara\n"
        "user: my name is Sara\n\nNew message:\nwhat is my name?"
    )
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert "Sara" in response.text


# -- full offline integration ---------------------------------------------


def test_end_to_end_offline_math_through_the_real_tool_loop():
    agent = Agent(
        DemoProvider(),
        tool_registry=create_tool_registry(),
        tool_executor=ToolExecutor(),
    )

    result = agent.run("what is 144 / 12?")

    assert result.success
    assert result.output == "144 / 12 equals 12."


def test_end_to_end_offline_chain_math_through_the_real_tool_loop():
    agent = Agent(
        DemoProvider(),
        tool_registry=create_tool_registry(),
        tool_executor=ToolExecutor(),
    )

    result = agent.run("what is 2+2*3?")

    assert result.success
    assert result.output == "2+2*3 equals 8."


def test_calls_counter_counts_every_generate_response_call(provider: DemoProvider):
    provider.generate_response("hello")
    provider.generate_response("hello")

    assert provider.calls == 2


def test_same_input_same_answer(provider: DemoProvider):
    first = provider.generate_response("what color is the sky?")
    second = provider.generate_response("what color is the sky?")

    assert first == second


# -- generate() and the router contract -----------------------------------


def test_generate_returns_plain_text(provider: DemoProvider):
    assert "Blue" in provider.generate("what color is the sky?")


def test_generate_answers_a_router_decision_with_a_mentioned_name(provider: DemoProvider):
    composed = (
        "Pick the agent.\n\nAvailable agents:\n- greeter\n- math\n\n"
        "User prompt:\nplease let the math agent answer\n\n"
        "Answer with exactly one agent name and nothing else."
    )

    assert provider.generate(composed) == "math"


def test_generate_answers_a_router_decision_with_the_first_listed_name(provider: DemoProvider):
    composed = (
        "Pick the agent.\n\nAvailable agents:\n- greeter\n- math\n\n"
        "User prompt:\nwhat is 144 / 12?\n\n"
        "Answer with exactly one agent name and nothing else."
    )

    assert provider.generate(composed) == "greeter"


def test_generate_outside_a_router_decision_answers_normally(provider: DemoProvider):
    assert "Hello" in provider.generate("hello")


# -- streaming (ADR 0009) --------------------------------------------------


def test_stream_yields_word_deltas_then_the_final_text(provider: DemoProvider):
    events = list(provider.stream_response("hello"))

    deltas = [e for e in events if isinstance(e, StreamTextDelta)]
    finals = [e for e in events if isinstance(e, TextResponse)]

    assert len(deltas) > 1
    assert len(finals) == 1
    assert "".join(d.text for d in deltas).strip() == finals[0].text.strip()


def test_stream_passes_tools_through(provider: DemoProvider):
    events = list(provider.stream_response("2+2", tools=(ToolSpec("calculator", "math"),)))

    assert isinstance(events[-1], ToolCallRequest)


def test_agent_streams_the_demo_brain_word_by_word():
    agent = Agent(DemoProvider())
    chunks: list[str] = []

    result = agent.run("what color is the sky?", on_delta=chunks.append)

    assert result.success
    assert len(chunks) > 1
    assert "".join(chunks).strip() == result.output.strip()


# -- the knowledge sheet (v1.8.0, ADR 0017) --------------------------------


def test_chess_question_names_white(provider: DemoProvider):
    response = provider.generate_response("who start first in chess? black or white")

    assert isinstance(response, TextResponse)
    assert "White moves first" in response.text
    assert "black never starts" in response.text


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("why is the sky blue?", "Rayleigh"),
        ("how fast does light travel?", "299,792,458"),
        ("how far is the sun?", "149.6"),
        ("how far is the moon?", "384,400"),
        ("what is the boiling point of water?", "100 °C"),
        ("what is a normal body temperature?", "37 °C"),
        ("what is pi?", "3.141592653589793"),
        ("how many days are in a year?", "365"),
        ("what is a leap year?", "366"),
        ("how many continents are there?", "Seven"),
        ("how many oceans are there?", "Five"),
        ("how many planets are in the solar system?", "Eight"),
        ("what is the tallest mountain?", "Everest"),
        ("what is the largest animal?", "blue whale"),
        ("what is the fastest land animal?", "cheetah"),
        ("how many bones does a human have?", "206"),
    ],
)
def test_knowledge_sheet_entries(provider: DemoProvider, prompt: str, expected: str):
    response = provider.generate_response(prompt)

    assert isinstance(response, TextResponse)
    assert expected in response.text


def test_knowledge_is_case_and_punctuation_insensitive(provider: DemoProvider):
    response = provider.generate_response("WHO Moves FIRST In CHESS")

    assert isinstance(response, TextResponse)
    assert "White moves first" in response.text


def test_knowledge_scoring_keeps_sun_and_moon_apart(provider: DemoProvider):
    response = provider.generate_response("how far is the moon from the earth")

    assert isinstance(response, TextResponse)
    assert "384,400" in response.text
    assert "149.6" not in response.text


@pytest.mark.parametrize(
    "prompt",
    [
        "who start first in chess? black or white",
        "why is the sky blue?",
        "how far is the moon?",
        "what is pi?",
        "how many planets are in the solar system?",
        "how many bones does a human have?",
    ],
)
def test_knowledge_answers_are_deterministic(provider: DemoProvider, prompt: str):
    first = provider.generate_response(prompt)
    second = provider.generate_response(prompt)

    assert first == second


# -- did-you-mean suggestions (v1.8.0) --------------------------------------


def test_color_miss_suggests_a_close_noun(provider: DemoProvider):
    response = provider.generate_response("what color is the skys?")

    assert isinstance(response, TextResponse)
    assert "did you mean" in response.text.lower()
    assert "sky" in response.text.lower()


def test_fallback_suggests_a_close_topic(provider: DemoProvider):
    response = provider.generate_response("tell me about the moon landing")

    assert isinstance(response, TextResponse)
    assert "did you mean" in response.text.lower()
    assert "moon" in response.text.lower()
    assert "OpenAI" in response.text


def test_fallback_without_a_nearby_topic_is_the_plain_reply(provider: DemoProvider):
    response = provider.generate_response("explain quantum entanglement")

    assert isinstance(response, TextResponse)
    assert response.text == _FALLBACK_REPLY


def test_known_topics_still_answer_instead_of_suggesting(provider: DemoProvider):
    response = provider.generate_response("what is the speed of light?")

    assert isinstance(response, TextResponse)
    assert "299,792,458" in response.text
    assert "did you mean" not in response.text.lower()
