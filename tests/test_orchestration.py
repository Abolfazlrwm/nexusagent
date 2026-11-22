"""Multi-agent orchestration (ADR 0015): AgentTeam, TeamResult, provider router.

Offline, deterministic tests. Every behavior is pinned: eager validation,
routing-failures-become-failed-results, delegation semantics (the member's
own loop, tools and memory run unchanged), the streaming passthrough, and
the documented deterministic parse of ``create_provider_router``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

import pytest

from nexusagent.agent import Agent
from nexusagent.memory import InMemoryMemory
from nexusagent.orchestration import (
    DEFAULT_ROUTER_INSTRUCTION,
    AgentTeam,
    TeamResult,
    create_provider_router,
)
from nexusagent.provider import Provider, ProviderResponseError, TextResponse
from nexusagent.providers import FakeProvider, ScriptedProvider
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class UppercaseTool(Tool):
    def __init__(self) -> None:
        super().__init__("uppercase", "Uppercases its input")

    def execute(self, input_data: str) -> str:
        return input_data.upper()


class PassthroughExecutor(ToolExecutor):
    def execute(self, tool: Tool, input_data: str) -> str:
        return tool.execute(input_data)


def _greeter_agent() -> Agent:
    """A plain agent: text in, text out, no tools."""
    return Agent(ScriptedProvider([TextResponse("hello from the greeter")]))


def _team(
    router: Callable[[str], str] | None = None,
    *,
    greeter: Agent | None = None,
) -> AgentTeam:
    agents = {"greeter": greeter if greeter is not None else _greeter_agent()}
    return AgentTeam(agents, router if router is not None else (lambda prompt: "greeter"))


# ---------------------------------------------------------------------------
# TeamResult
# ---------------------------------------------------------------------------


def test_team_result_has_output_success_and_agent_name_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(TeamResult)}

    assert field_names == {"output", "success", "agent_name"}


def test_team_result_is_immutable() -> None:
    result = TeamResult(output="hi", success=True, agent_name="greeter")

    with pytest.raises(AttributeError):
        result.output = "changed"  # type: ignore[misc]


def test_team_result_supports_value_equality() -> None:
    assert TeamResult("a", True, "x") == TeamResult("a", True, "x")
    assert TeamResult("a", True, "x") != TeamResult("a", True, "y")


# ---------------------------------------------------------------------------
# AgentTeam construction
# ---------------------------------------------------------------------------


def test_team_requires_a_mapping() -> None:
    with pytest.raises(TypeError, match="mapping"):
        AgentTeam([("greeter", _greeter_agent())], lambda prompt: "greeter")  # type: ignore[arg-type]


def test_team_requires_a_non_empty_mapping() -> None:
    with pytest.raises(ValueError, match="empty"):
        AgentTeam({}, lambda prompt: "greeter")


def test_team_requires_string_names() -> None:
    with pytest.raises(TypeError, match="strings"):
        AgentTeam({1: _greeter_agent()}, lambda prompt: "greeter")  # type: ignore[dict-item]


def test_team_requires_non_blank_names() -> None:
    with pytest.raises(ValueError, match="whitespace"):
        AgentTeam({"   ": _greeter_agent()}, lambda prompt: "greeter")


def test_team_requires_agent_instances() -> None:
    with pytest.raises(TypeError, match="Agent instance"):
        AgentTeam({"greeter": "not an agent"}, lambda prompt: "greeter")  # type: ignore[dict-item]


def test_team_requires_a_callable_router() -> None:
    with pytest.raises(TypeError, match="callable"):
        AgentTeam({"greeter": _greeter_agent()}, "greeter")  # type: ignore[arg-type]


def test_team_agents_property_is_a_read_only_view() -> None:
    team = _team()

    assert set(team.agents) == {"greeter"}
    with pytest.raises(TypeError):
        team.agents["intruder"] = _greeter_agent()  # type: ignore[index]


def test_team_agents_property_exposes_the_members() -> None:
    greeter = _greeter_agent()
    team = AgentTeam({"greeter": greeter}, lambda prompt: "greeter")

    assert set(team.agents) == {"greeter"}
    assert team.agents["greeter"] is greeter


# ---------------------------------------------------------------------------
# AgentTeam.run input validation
# ---------------------------------------------------------------------------


def test_team_run_rejects_non_string_input() -> None:
    with pytest.raises(TypeError, match="string"):
        _team().run(123)  # type: ignore[arg-type]


def test_team_run_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        _team().run("")


def test_team_run_rejects_whitespace_only_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        _team().run("   \n\t ")


# ---------------------------------------------------------------------------
# Routing failures become failed results
# ---------------------------------------------------------------------------


def test_router_exception_becomes_a_failed_result() -> None:
    def broken_router(prompt: str) -> str:
        raise RuntimeError("router exploded")

    result = _team(broken_router).run("hello")

    assert result.success is False
    assert result.agent_name == ""
    assert "routing error" in result.output
    assert "router exploded" in result.output


def test_router_returning_non_string_becomes_a_failed_result() -> None:
    result = _team(lambda prompt: 42).run("hello")  # type: ignore[arg-type,return-value]

    assert result.success is False
    assert result.agent_name == ""
    assert "routing error" in result.output
    assert "expected str" in result.output


def test_router_returning_unknown_name_becomes_a_failed_result() -> None:
    result = _team(lambda prompt: "nobody").run("hello")

    assert result.success is False
    assert result.agent_name == ""
    assert "'nobody'" in result.output
    assert "greeter" in result.output


def test_router_name_is_stripped_before_lookup() -> None:
    result = _team(lambda prompt: "  greeter  ").run("hello")

    assert result.success is True
    assert result.agent_name == "greeter"


# ---------------------------------------------------------------------------
# Delegation semantics
# ---------------------------------------------------------------------------


def test_team_returns_the_selected_agents_answer() -> None:
    result = _team().run("hello")

    assert result == TeamResult(output="hello from the greeter", success=True, agent_name="greeter")


def test_team_routes_to_the_agent_the_router_names() -> None:
    greeter = _greeter_agent()
    bye = Agent(ScriptedProvider([TextResponse("bye from bye-er")]))
    team = AgentTeam(
        {"greeter": greeter, "bye": bye},
        lambda prompt: "bye" if "goodbye" in prompt else "greeter",
    )

    assert team.run("goodbye now").agent_name == "bye"
    assert team.run("hi there").agent_name == "greeter"


def test_member_agent_keeps_its_own_memory_behavior() -> None:
    memory = InMemoryMemory()
    greeter = Agent(
        ScriptedProvider([TextResponse("first answer"), TextResponse("second answer")]),
        memory=memory,
    )
    team = _team(greeter=greeter)

    first = team.run("hello")
    second = team.run("hello again")

    assert first.success and second.success
    assert second.output == "second answer"
    # the member's memory saw exactly its own two exchanges
    assert len(memory) == 4
    assert memory.history()[0].text == "hello"
    assert memory.history()[2].text == "hello again"


def test_member_agent_tool_loop_runs_unchanged_inside_the_team() -> None:
    registry = ToolRegistry()
    registry.register(UppercaseTool())
    scripted = ScriptedProvider(
        [
            # the team routes to this agent; the model asks for the tool...
            _tool_call(),
            # ...and after the tool result comes back, answers with text
            TextResponse("UPPERCASED"),
        ]
    )
    member = Agent(scripted, tool_registry=registry, tool_executor=PassthroughExecutor())
    team = AgentTeam({"shouter": member}, lambda prompt: "shouter")

    result = team.run("shout hello")

    assert result.success is True
    assert result.agent_name == "shouter"
    assert result.output == "UPPERCASED"
    assert len(scripted.calls) == 2
    tool_results = scripted.calls[1][2]
    assert len(tool_results) == 1
    assert tool_results[0].output == "HELLO"


def test_team_forwards_on_delta_to_the_selected_agent() -> None:
    deltas: list[str] = []

    class DeltaProvider(Provider):
        def generate(self, prompt: str) -> str:
            return "assembled answer"

        def stream_response(self, prompt: str, **kwargs: object) -> Sequence[object]:
            from nexusagent.provider import StreamTextDelta

            yield StreamTextDelta("as")
            yield StreamTextDelta("sembled")
            yield StreamTextDelta(" answer")
            yield TextResponse("assembled answer")

    team = AgentTeam({"streamer": Agent(DeltaProvider())}, lambda prompt: "streamer")
    result = team.run("hello", on_delta=deltas.append)

    assert result.success is True
    assert result.output == "assembled answer"
    assert deltas == ["as", "sembled", " answer"]


def test_member_failure_is_reported_as_a_failed_team_result() -> None:
    class ExplodingProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            raise ValueError("backend down")

    team = AgentTeam({"doomed": Agent(ExplodingProvider())}, lambda prompt: "doomed")
    result = team.run("hello")

    assert result.success is False
    assert result.agent_name == "doomed"
    assert "provider error" in result.output


def _tool_call() -> object:
    from nexusagent.provider import ToolCallRequest

    return ToolCallRequest(tool_name="uppercase", tool_input="hello")


# ---------------------------------------------------------------------------
# create_provider_router
# ---------------------------------------------------------------------------


def test_provider_router_requires_a_provider() -> None:
    with pytest.raises(TypeError, match="Provider"):
        create_provider_router("not a provider", ["a"])  # type: ignore[arg-type]


def test_provider_router_rejects_non_sequence_names() -> None:
    with pytest.raises(TypeError, match="sequence"):
        create_provider_router(FakeProvider(), {"a", "b"})  # type: ignore[arg-type]


def test_provider_router_rejects_a_string_as_names() -> None:
    with pytest.raises(TypeError, match="sequence"):
        create_provider_router(FakeProvider(), "abc")  # type: ignore[arg-type]


def test_provider_router_requires_names() -> None:
    with pytest.raises(ValueError, match="empty"):
        create_provider_router(FakeProvider(), [])


def test_provider_router_rejects_non_string_names() -> None:
    with pytest.raises(TypeError, match="strings"):
        create_provider_router(FakeProvider(), [1])  # type: ignore[list-item]


def test_provider_router_rejects_blank_names() -> None:
    with pytest.raises(ValueError, match="whitespace"):
        create_provider_router(FakeProvider(), ["  "])


def test_provider_router_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        create_provider_router(FakeProvider(), ["a", "a"])


def test_provider_router_composes_instruction_listing_and_prompt() -> None:
    calls: list[str] = []

    class RecordingProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            calls.append(prompt)
            return "math"

    router = create_provider_router(
        RecordingProvider(),
        ["math", "greeter"],
        instruction="pick one",
    )
    chosen = router("what is 2 + 2?")

    assert chosen == "math"
    assert len(calls) == 1
    composed = calls[0]
    assert "pick one" in composed
    assert "- math" in composed
    assert "- greeter" in composed
    assert "what is 2 + 2?" in composed
    assert DEFAULT_ROUTER_INSTRUCTION != "pick one"


def test_provider_router_default_instruction_is_used_verbatim() -> None:
    calls: list[str] = []

    class RecordingProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            calls.append(prompt)
            return "greeter"

    router = create_provider_router(RecordingProvider(), ["greeter"])
    router("hi")

    assert DEFAULT_ROUTER_INSTRUCTION in calls[0]


def test_provider_router_exact_match_wins() -> None:
    router = create_provider_router(fixed_reply_provider("math"), ["math", "greeter"])

    assert router("what is 2 + 2?") == "math"


def fixed_reply_provider(reply: str) -> Provider:
    """A minimal Provider whose generate() always returns ``reply``."""

    class FixedReplyProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            return reply

    return FixedReplyProvider()


def test_provider_router_strips_whitespace_before_matching() -> None:
    router = create_provider_router(fixed_reply_provider("  greeter \n"), ["math", "greeter"])

    assert router("hello") == "greeter"


def test_provider_router_is_case_insensitive() -> None:
    router = create_provider_router(fixed_reply_provider("MATH"), ["math", "greeter"])

    assert router("what is 2 + 2?") == "math"


def test_provider_router_finds_a_name_embedded_in_a_sentence() -> None:
    router = create_provider_router(
        fixed_reply_provider("The math agent should take this one."), ["greeter", "math"]
    )

    assert router("what is 2 + 2?") == "math"


def test_provider_router_embedded_match_prefers_the_earliest_occurrence() -> None:
    router = create_provider_router(
        fixed_reply_provider("math or greeter? I think greeter is best."),
        ["math", "greeter"],
    )

    # "math" appears at position 0, "greeter" later — earliest wins
    assert router("route this") == "math"


def test_provider_router_position_tie_prefers_the_earlier_listed_name() -> None:
    router = create_provider_router(
        fixed_reply_provider("mathematics is the domain here"),
        ["math", "mathematics"],
    )

    # "math" and "mathematics" both occur at position 0 — the tie resolves
    # to the earlier listed name, per the documented rule.
    assert router("route this") == "math"


def test_provider_router_missing_name_raises_provider_response_error() -> None:
    router = create_provider_router(fixed_reply_provider("I cannot decide."), ["math", "greeter"])

    with pytest.raises(ProviderResponseError, match="did not name"):
        router("route this")


def test_provider_router_rejects_non_string_prompts() -> None:
    router = create_provider_router(FakeProvider(), ["math"])

    with pytest.raises(TypeError, match="string"):
        router(123)  # type: ignore[arg-type]


def test_provider_router_rejects_empty_prompts() -> None:
    router = create_provider_router(FakeProvider(), ["math"])

    with pytest.raises(ValueError, match="empty"):
        router("   ")


def test_provider_router_rejects_non_string_replies() -> None:
    class NonStringReplyProvider(FakeProvider):
        def generate(self, prompt: str):
            return 123  # violates the Provider contract on purpose

    router = create_provider_router(NonStringReplyProvider(), ["math"])

    with pytest.raises(ProviderResponseError, match="non-string"):
        router("route this")


def test_provider_router_propagates_provider_errors() -> None:
    class ExplodingProvider(FakeProvider):
        def generate(self, prompt: str) -> str:
            raise ValueError("backend down")

    router = create_provider_router(ExplodingProvider(), ["math"])

    with pytest.raises(ValueError, match="backend down"):
        router("route this")


def test_routing_failure_from_provider_router_reaches_the_team_result() -> None:
    router = create_provider_router(fixed_reply_provider("no idea"), ["math", "greeter"])
    team = _team(router)

    result = team.run("hello")

    assert result.success is False
    assert result.agent_name == ""
    assert "routing error" in result.output


def test_end_to_end_team_with_provider_router() -> None:
    router_provider = ScriptedProvider(
        [TextResponse("math"), TextResponse("greeter")],
    )
    router = create_provider_router(router_provider, ["greeter", "math"])
    math = Agent(FakeProvider())  # "fake response: ..." — any Agent works
    greeter = _greeter_agent()
    team = AgentTeam({"greeter": greeter, "math": math}, router)

    assert team.run("what is 2 + 2?").agent_name == "math"
    assert team.run("hello").agent_name == "greeter"
