"""Contract tests for in-process conversation memory (ADR 0012).

Memory is opt-in: without it every prompt the provider sees is exactly
the user input. With it, completed exchanges are remembered and composed
into the next run's prompt as a text transcript, and the Provider
contract stays untouched. These tests pin that behavior: the dataclass
and storage validation, the transcript format, the agent recording rules
(successful runs only, sync and async), the runtime/factory wiring, and
the public-surface additions.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Iterator

import pytest

from nexusagent import (
    Agent,
    AgentResult,
    AsyncAgent,
    AsyncRuntime,
    ConversationTurn,
    InMemoryMemory,
    Memory,
    Provider,
    ProviderResponse,
    Runtime,
    ScriptedProvider,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    create_async_runtime,
    create_runtime,
)
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.memory import (
    ASSISTANT_ROLE,
    USER_ROLE,
    compose_prompt,
)
from nexusagent.provider import AsyncProvider


def turn(role: str, text: str) -> ConversationTurn:
    return ConversationTurn(role, text)


# --- ConversationTurn ------------------------------------------------------


def test_conversation_turn_is_frozen() -> None:
    t = turn(USER_ROLE, "hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.role = ASSISTANT_ROLE  # type: ignore[misc]


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_conversation_turn_accepts_valid_roles(role: str) -> None:
    assert turn(role, "text").role == role


@pytest.mark.parametrize("role", ["system", "tool", "", "USER", "user "])
def test_conversation_turn_rejects_unknown_roles(role: str) -> None:
    with pytest.raises(ValueError, match="role must be one of"):
        turn(role, "text")


def test_conversation_turn_rejects_non_string_role() -> None:
    with pytest.raises(TypeError, match="role must be a string"):
        turn(1, "text")  # type: ignore[arg-type]


def test_conversation_turn_rejects_non_string_text() -> None:
    with pytest.raises(TypeError, match="text must be a string"):
        turn(USER_ROLE, None)  # type: ignore[arg-type]


# --- Memory contract --------------------------------------------------------


def test_memory_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Memory()  # type: ignore[abstract]


class _RecordingMemory(Memory):
    """Minimal custom backend proving the ABC is the whole contract."""

    def __init__(self) -> None:
        self._turns: list[ConversationTurn] = []

    def append(self, turn: ConversationTurn) -> None:
        self._turns.append(turn)

    def history(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    def clear(self) -> None:
        self._turns.clear()


def test_custom_memory_subclass_satisfies_the_contract() -> None:
    memory = _RecordingMemory()
    memory.append(turn(USER_ROLE, "a"))
    memory.append(turn(ASSISTANT_ROLE, "b"))
    assert len(memory) == 2
    assert memory.history() == (turn(USER_ROLE, "a"), turn(ASSISTANT_ROLE, "b"))
    memory.clear()
    assert memory.history() == ()
    assert len(memory) == 0


# --- InMemoryMemory ---------------------------------------------------------


def test_in_memory_memory_defaults_and_order() -> None:
    memory = InMemoryMemory()
    memory.append(turn(USER_ROLE, "first"))
    memory.append(turn(ASSISTANT_ROLE, "second"))
    assert memory.history() == (turn(USER_ROLE, "first"), turn(ASSISTANT_ROLE, "second"))
    assert len(memory) == 2


def test_in_memory_memory_evicts_oldest_beyond_the_cap() -> None:
    memory = InMemoryMemory(max_turns=2)
    memory.append(turn(USER_ROLE, "1"))
    memory.append(turn(ASSISTANT_ROLE, "2"))
    memory.append(turn(USER_ROLE, "3"))
    assert [t.text for t in memory.history()] == ["2", "3"]


def test_in_memory_memory_cap_of_one_keeps_only_the_last_turn() -> None:
    memory = InMemoryMemory(max_turns=1)
    memory.append(turn(USER_ROLE, "1"))
    memory.append(turn(ASSISTANT_ROLE, "2"))
    assert [t.text for t in memory.history()] == ["2"]


def test_in_memory_memory_clear() -> None:
    memory = InMemoryMemory()
    memory.append(turn(USER_ROLE, "1"))
    memory.clear()
    assert memory.history() == ()


def test_in_memory_memory_rejects_non_turn_append() -> None:
    memory = InMemoryMemory()
    with pytest.raises(TypeError, match="turn must be a ConversationTurn"):
        memory.append("user: hello")  # type: ignore[arg-type]


@pytest.mark.parametrize("max_turns", [0, -1, -100])
def test_in_memory_memory_rejects_non_positive_max_turns(max_turns: int) -> None:
    with pytest.raises(ValueError, match="max_turns must be at least 1"):
        InMemoryMemory(max_turns=max_turns)


@pytest.mark.parametrize("max_turns", [1.5, "10", None, True])
def test_in_memory_memory_rejects_non_integer_max_turns(max_turns: object) -> None:
    with pytest.raises(TypeError, match="max_turns must be an integer"):
        InMemoryMemory(max_turns=max_turns)  # type: ignore[arg-type]


def test_in_memory_memory_history_is_a_snapshot() -> None:
    memory = InMemoryMemory()
    memory.append(turn(USER_ROLE, "1"))
    history = memory.history()
    memory.append(turn(ASSISTANT_ROLE, "2"))
    assert len(history) == 1
    assert len(memory.history()) == 2


# --- compose_prompt ---------------------------------------------------------


def test_compose_prompt_with_empty_history_is_the_input_unchanged() -> None:
    input_text = "What is 19 + 23?"
    assert compose_prompt(input_text, ()) is input_text


def test_compose_prompt_transcript_format() -> None:
    history = (
        turn(USER_ROLE, "My name is Sara"),
        turn(ASSISTANT_ROLE, "Nice to meet you, Sara!"),
    )
    assert compose_prompt("What is my name?", history) == (
        "Previous conversation (oldest first):\n"
        "user: My name is Sara\n"
        "assistant: Nice to meet you, Sara!\n"
        "\n"
        "Respond to this new user message:\n"
        "What is my name?"
    )


def test_compose_prompt_keeps_turns_oldest_first() -> None:
    history = (turn(USER_ROLE, "first"), turn(USER_ROLE, "second"))
    composed = compose_prompt("third", history)
    assert composed.index("user: first") < composed.index("user: second")


def test_compose_prompt_with_single_turn() -> None:
    composed = compose_prompt("next", (turn(ASSISTANT_ROLE, "only"),))
    assert composed == (
        "Previous conversation (oldest first):\n"
        "assistant: only\n"
        "\n"
        "Respond to this new user message:\n"
        "next"
    )


# --- Agent integration ------------------------------------------------------


def test_agent_without_memory_sends_the_input_verbatim() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    agent = Agent(provider)
    result = agent.run("hello")
    assert result.success
    assert provider.calls[0][0] == "hello"


def test_agent_with_empty_memory_sends_the_input_verbatim() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    agent = Agent(provider, memory=InMemoryMemory())
    result = agent.run("hello")
    assert result.success
    assert provider.calls[0][0] == "hello"
    assert agent.memory is not None
    assert agent.memory.history() == (turn(USER_ROLE, "hello"), turn(ASSISTANT_ROLE, "answer"))


def test_agent_records_user_and_assistant_turns_on_success() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)
    result = agent.run("hello")
    assert result.success
    assert memory.history() == (turn(USER_ROLE, "hello"), turn(ASSISTANT_ROLE, "answer"))


def test_agent_composes_remembered_turns_into_the_next_prompt() -> None:
    provider = ScriptedProvider([TextResponse("first answer"), TextResponse("second answer")])
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)

    assert agent.run("My name is Sara").success
    assert agent.run("What is my name?").success

    assert len(provider.calls) == 2
    first_prompt, second_prompt = provider.calls[0][0], provider.calls[1][0]
    assert first_prompt == "My name is Sara"
    assert second_prompt == (
        "Previous conversation (oldest first):\n"
        "user: My name is Sara\n"
        "assistant: first answer\n"
        "\n"
        "Respond to this new user message:\n"
        "What is my name?"
    )


def test_agent_failed_run_records_nothing() -> None:
    class _ExplodingProvider(Provider):
        def generate(self, prompt: str) -> str:
            raise RuntimeError("backend down")

    memory = InMemoryMemory()
    agent = Agent(_ExplodingProvider(), memory=memory)
    result = agent.run("hello")
    assert not result.success
    assert memory.history() == ()


def test_agent_tool_loop_run_records_only_the_completed_exchange() -> None:
    provider = ScriptedProvider(
        [
            ToolCallRequest("echo", "repeat me"),
            TextResponse("final answer"),
        ]
    )
    memory = InMemoryMemory()

    from nexusagent import ToolRegistry
    from nexusagent.echo_tool import EchoTool
    from nexusagent.tool_executor import ToolExecutor

    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = Agent(provider, tool_registry=registry, tool_executor=ToolExecutor(), memory=memory)

    result = agent.run("run the tool")
    assert result.success and result.output == "final answer"

    # One exchange, not one turn per tool iteration: the loop's tool
    # traffic stays inside the run; memory holds its input and output.
    expected = (
        turn(USER_ROLE, "run the tool"),
        turn(ASSISTANT_ROLE, "final answer"),
    )
    assert memory.history() == expected


def test_agent_max_iterations_exhaustion_records_nothing() -> None:
    provider = ScriptedProvider([ToolCallRequest("echo", "again") for _ in range(3)])
    memory = InMemoryMemory()

    from nexusagent import ToolRegistry
    from nexusagent.echo_tool import EchoTool
    from nexusagent.tool_executor import ToolExecutor

    registry = ToolRegistry()
    registry.register(EchoTool())
    agent = Agent(
        provider,
        tool_registry=registry,
        tool_executor=ToolExecutor(),
        max_iterations=3,
        memory=memory,
    )

    result = agent.run("loop forever")
    assert not result.success
    assert memory.history() == ()


def test_agent_requested_tool_without_tools_records_nothing() -> None:
    provider = ScriptedProvider([ToolCallRequest("echo", "input")])
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)
    result = agent.run("use a tool")
    assert not result.success
    assert memory.history() == ()


def test_agent_streaming_run_records_the_final_output() -> None:
    class _StreamingScriptedProvider(ScriptedProvider):
        def stream_response(
            self,
            prompt: str,
            *,
            tools: tuple = (),
            tool_results: tuple = (),
        ) -> Iterator[ProviderResponse]:
            from nexusagent import StreamTextDelta

            yield StreamTextDelta("final ")
            yield StreamTextDelta("answer")
            yield TextResponse("final answer")

    memory = InMemoryMemory()
    agent = Agent(_StreamingScriptedProvider([TextResponse("final answer")]), memory=memory)
    deltas: list[str] = []
    result = agent.run("hello", on_delta=deltas.append)

    assert result.success and result.output == "final answer"
    assert deltas == ["final ", "answer"]
    assert memory.history() == (turn(USER_ROLE, "hello"), turn(ASSISTANT_ROLE, "final answer"))


def test_agent_streaming_failure_records_nothing() -> None:
    class _BrokenStreamProvider(ScriptedProvider):
        def stream_response(
            self,
            prompt: str,
            *,
            tools: tuple = (),
            tool_results: tuple = (),
        ) -> Iterator[ProviderResponse]:
            raise RuntimeError("stream died")
            yield TextResponse("never reached")  # pragma: no cover

    memory = InMemoryMemory()
    agent = Agent(_BrokenStreamProvider([]), memory=memory)
    result = agent.run("hello", on_delta=lambda _: None)
    assert not result.success
    assert memory.history() == ()


def test_agent_memory_records_input_even_with_surrounding_whitespace() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)
    agent.run("  spaced input  ")
    assert memory.history() == (
        turn(USER_ROLE, "  spaced input  "),
        turn(ASSISTANT_ROLE, "answer"),
    )


def test_agent_shares_memory_across_instances() -> None:
    first_provider = ScriptedProvider([TextResponse("first answer")])
    second_provider = ScriptedProvider([TextResponse("second answer")])
    memory = InMemoryMemory()

    Agent(first_provider, memory=memory).run("first question")
    Agent(second_provider, memory=memory).run("second question")

    assert [t.text for t in memory.history()] == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]


def test_agent_rejects_non_memory_object() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    with pytest.raises(TypeError, match="memory must be a Memory instance"):
        Agent(provider, memory="remember everything")  # type: ignore[arg-type]


# --- AsyncAgent integration -------------------------------------------------


class _AsyncScriptedProvider(AsyncProvider):
    """Async mirror of ScriptedProvider for the memory contract tests."""

    def __init__(self, responses: list[ProviderResponse]) -> None:
        self._responses = list(responses)
        self._position = 0
        self.calls: list[tuple[str, tuple, tuple]] = []

    async def generate(self, prompt: str) -> str:
        raise AssertionError("not used in these tests")

    async def generate_response(
        self,
        prompt: str,
        *,
        tools: tuple = (),
        tool_results: tuple = (),
    ) -> ProviderResponse:
        self.calls.append((prompt, tools, tool_results))
        if self._position >= len(self._responses):
            raise RuntimeError("no more scripted responses")
        response = self._responses[self._position]
        self._position += 1
        return response

    def stream_response(
        self,
        prompt: str,
        *,
        tools: tuple = (),
        tool_results: tuple = (),
    ) -> AsyncIterator[ProviderResponse]:
        raise AssertionError("not used in these tests")


async def _run(agent: AsyncAgent, text: str) -> AgentResult:
    return await agent.run(text)


def test_async_agent_records_and_composes_turns() -> None:
    import asyncio

    provider = _AsyncScriptedProvider([TextResponse("first answer"), TextResponse("second answer")])
    memory = InMemoryMemory()
    agent = AsyncAgent(provider, memory=memory)  # type: ignore[arg-type]

    first = asyncio.run(_run(agent, "My name is Sara"))
    second = asyncio.run(_run(agent, "What is my name?"))

    assert first.success and second.success
    assert memory.history() == (
        turn(USER_ROLE, "My name is Sara"),
        turn(ASSISTANT_ROLE, "first answer"),
        turn(USER_ROLE, "What is my name?"),
        turn(ASSISTANT_ROLE, "second answer"),
    )
    assert provider.calls[0][0] == "My name is Sara"
    assert provider.calls[1][0] == (
        "Previous conversation (oldest first):\n"
        "user: My name is Sara\n"
        "assistant: first answer\n"
        "\n"
        "Respond to this new user message:\n"
        "What is my name?"
    )


def test_async_agent_failed_run_records_nothing() -> None:
    import asyncio

    class _ExplodingAsyncProvider(_AsyncScriptedProvider):
        async def generate_response(
            self,
            prompt: str,
            *,
            tools: tuple = (),
            tool_results: tuple = (),
        ) -> ProviderResponse:
            raise RuntimeError("backend down")

    memory = InMemoryMemory()
    agent = AsyncAgent(_ExplodingAsyncProvider([]), memory=memory)  # type: ignore[arg-type]
    result = asyncio.run(_run(agent, "hello"))
    assert not result.success
    assert memory.history() == ()


def test_async_agent_rejects_non_memory_object() -> None:
    provider = _AsyncScriptedProvider([TextResponse("answer")])
    with pytest.raises(TypeError, match="memory must be a Memory instance"):
        AsyncAgent(provider, memory=42)  # type: ignore[arg-type]


def test_sync_provider_adapter_with_memory() -> None:
    import asyncio

    provider = ScriptedProvider([TextResponse("answer"), TextResponse("answer 2")])
    memory = InMemoryMemory()
    agent = AsyncAgent(SyncProviderAdapter(provider), memory=memory)

    first = asyncio.run(_run(agent, "first question"))
    second = asyncio.run(_run(agent, "second question"))

    assert first.success and second.success
    assert provider.calls[0][0] == "first question"
    assert provider.calls[1][0].startswith("Previous conversation (oldest first):")
    assert memory.history() == (
        turn(USER_ROLE, "first question"),
        turn(ASSISTANT_ROLE, "answer"),
        turn(USER_ROLE, "second question"),
        turn(ASSISTANT_ROLE, "answer 2"),
    )


# --- Runtime and factory wiring ---------------------------------------------


def test_runtime_exposes_agent_memory() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)
    runtime = Runtime(agent)
    assert runtime.memory is memory


def test_runtime_memory_is_none_without_memory() -> None:
    provider = ScriptedProvider([TextResponse("answer")])
    runtime = Runtime(Agent(provider))
    assert runtime.memory is None


def test_create_runtime_wires_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_PROVIDER", "fake")
    memory = InMemoryMemory()
    runtime = create_runtime(memory=memory)
    assert runtime.memory is memory
    assert runtime.run("hello").success
    assert runtime.memory is not None and len(runtime.memory) == 2


def test_async_runtime_exposes_agent_memory() -> None:
    provider = _AsyncScriptedProvider([TextResponse("answer")])
    memory = InMemoryMemory()
    agent = AsyncAgent(provider, memory=memory)  # type: ignore[arg-type]
    runtime = AsyncRuntime(agent)
    assert runtime.memory is memory


def test_create_async_runtime_wires_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_PROVIDER", "fake")
    memory = InMemoryMemory()
    runtime = create_async_runtime(memory=memory)
    assert runtime.memory is memory


def test_tool_result_error_flow_unaffected_by_memory() -> None:
    """A tool failure inside a run still becomes an error result, then the
    successful run records the completed exchange as usual."""
    provider = ScriptedProvider(
        [
            ToolCallRequest("missing_tool", "input"),
            TextResponse("recovered"),
        ]
    )
    memory = InMemoryMemory()

    from nexusagent import ToolRegistry
    from nexusagent.tool_executor import ToolExecutor

    registry = ToolRegistry()
    agent = Agent(provider, tool_registry=registry, tool_executor=ToolExecutor(), memory=memory)

    result = agent.run("try the missing tool")
    assert result.success and result.output == "recovered"
    assert ToolResult("x", "y", "z")  # sanity: the dataclass contract is unchanged
    assert memory.history() == (
        turn(USER_ROLE, "try the missing tool"),
        turn(ASSISTANT_ROLE, "recovered"),
    )
