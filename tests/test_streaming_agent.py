"""Contract tests for the streaming agent loop: Agent.run(on_delta=...) (ADR 0009)."""

from collections.abc import Iterator

import pytest

from nexusagent.agent import Agent, AgentResult
from nexusagent.echo_tool import EchoTool
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderResponseError,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.providers import FakeProvider, ScriptedProvider
from nexusagent.runtime import Runtime
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class StreamingProvider(Provider):
    """A provider that streams scripted events, one script entry per call."""

    def __init__(self, scripts: list[list[ProviderStreamEvent]]) -> None:
        self._scripts = scripts
        self._position = 0

    def generate(self, prompt: str) -> str:
        raise AssertionError("generate() must not be called during these tests")

    def stream_response(
        self,
        prompt: str,
        *,
        tools=(),
        tool_results=(),
    ) -> Iterator[ProviderStreamEvent]:
        script = self._scripts[self._position]
        self._position += 1
        yield from script


class StreamlessProvider(Provider):
    """A provider whose stream_response() must never be called."""

    def __init__(self) -> None:
        self.generate_response_calls = 0

    def generate(self, prompt: str) -> str:
        return f"plain: {prompt}"

    def generate_response(self, prompt, *, tools=(), tool_results=()):
        self.generate_response_calls += 1
        return TextResponse(f"plain: {prompt}")

    def stream_response(self, prompt, *, tools=(), tool_results=()):
        raise AssertionError("stream_response must not be used without on_delta")


def make_agent(provider, **kwargs) -> Agent:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return Agent(provider, tool_registry=registry, tool_executor=ToolExecutor(), **kwargs)


def collect_deltas(provider, input_text="hi", **kwargs):
    deltas: list[str] = []
    agent = Agent(provider, **kwargs)
    result = agent.run(input_text, on_delta=lambda text: deltas.append(text))
    return deltas, result


def make_tools() -> dict[str, object]:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return {"tool_registry": registry, "tool_executor": ToolExecutor()}


# --- Provider streaming contract --------------------------------------------------


def test_provider_default_stream_response_yields_single_final_event():
    provider = FakeProvider()
    events = list(provider.stream_response("hi"))
    assert events == [TextResponse("fake response: hi")]


def test_provider_default_stream_response_forwards_tools_and_results():
    provider = ScriptedProvider([TextResponse("done")])
    tools = (ToolSpec("upper", "Upper."),)
    results = (ToolResult("upper", "hi", "HI"),)

    events = list(provider.stream_response("hi", tools=tools, tool_results=results))

    assert events == [TextResponse("done")]
    assert provider.calls == [("hi", tools, results)]


# --- Agent streaming loop ---------------------------------------------------------


def test_agent_forwards_streamed_deltas_in_order():
    provider = StreamingProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )
    deltas, result = collect_deltas(provider)

    assert deltas == ["Hel", "lo"]
    assert result.success is True
    assert result.output == "Hello"


def test_agent_with_on_delta_none_never_uses_stream_response():
    provider = StreamlessProvider()
    agent = Agent(provider)
    result = agent.run("hi")

    assert result.success is True
    assert result.output == "plain: hi"
    assert provider.generate_response_calls == 1


def test_agent_non_streaming_provider_with_on_delta_stays_silent():
    deltas, result = collect_deltas(FakeProvider())

    assert deltas == []
    assert result.success is True
    assert result.output == "fake response: hi"


def test_agent_scripted_provider_stream_path_without_deltas():
    provider = ScriptedProvider([TextResponse("scripted")])
    deltas, result = collect_deltas(provider)

    assert deltas == []
    assert result.output == "scripted"


def test_agent_forwards_deltas_emitted_before_a_tool_request():
    provider = StreamingProvider(
        [
            [StreamTextDelta("Let me check."), ToolCallRequest("echo", "hi")],
            [StreamTextDelta("Final"), StreamTextDelta(" answer"), TextResponse("Final answer")],
        ]
    )
    deltas, result = collect_deltas(provider, **make_tools())

    assert deltas == ["Let me check.", "Final", " answer"]
    assert result.success is True
    assert result.output == "Final answer"


def test_agent_streaming_tool_loop_feeds_results_back():
    provider = StreamingProvider(
        [
            [ToolCallRequest("echo", "hi")],
            [StreamTextDelta("echo: hi"), TextResponse("echo: hi")],
        ]
    )
    deltas, result = collect_deltas(provider, **make_tools())

    assert deltas == ["echo: hi"]
    assert result.success is True
    assert result.output == "echo: hi"


def test_agent_stream_still_bounded_by_max_iterations():
    provider = StreamingProvider([[ToolCallRequest("echo", "x")]] * 5)

    deltas, result = collect_deltas(provider, **make_tools(), max_iterations=2)

    assert deltas == []
    assert result.success is False
    assert "maximum of 2 iterations" in result.output


def test_agent_on_delta_exception_aborts_the_run():
    provider = StreamingProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )

    def broken_on_delta(text: str) -> None:
        raise RuntimeError("sink closed")

    agent = Agent(provider)
    result = agent.run("hi", on_delta=broken_on_delta)

    assert result.success is False
    assert result.output == "provider error: sink closed"


def test_agent_stream_provider_error_becomes_failed_result():
    class ExplodingStreamProvider(StreamingProvider):
        def stream_response(self, prompt, *, tools=(), tool_results=()):
            raise ProviderResponseError("backend hung up")
            yield  # pragma: no cover — makes this a generator

    deltas, result = collect_deltas(ExplodingStreamProvider([]))

    assert deltas == []
    assert result.success is False
    assert result.output == "provider error: backend hung up"


def test_agent_stream_without_final_response_is_an_error():
    provider = StreamingProvider([[StreamTextDelta("only deltas")]])
    deltas, result = collect_deltas(provider)

    assert deltas == ["only deltas"]
    assert result.success is False
    assert result.output == "provider error: provider stream ended without a final response"


def test_agent_streaming_provider_ignores_junk_events():
    class JunkStreamProvider(StreamingProvider):
        def stream_response(self, prompt, *, tools=(), tool_results=()):
            yield StreamTextDelta("Hel")
            yield "not an event"  # type: ignore[misc]
            yield TextResponse("Hello")

    deltas, result = collect_deltas(JunkStreamProvider([[]]))

    assert deltas == ["Hel"]
    assert result.success is True
    assert result.output == "Hello"


def test_agent_run_type_validation_precedes_streaming():
    agent = Agent(FakeProvider())
    with pytest.raises(TypeError, match="input_text"):
        agent.run(123, on_delta=lambda text: None)  # type: ignore[arg-type]


# --- Runtime passthrough ----------------------------------------------------------


def test_runtime_run_forwards_on_delta_to_agent():
    seen: dict[str, object] = {}

    class RecordingAgent(Agent):
        def run(self, input_text: str, *, on_delta=None):
            seen["input_text"] = input_text
            seen["on_delta"] = on_delta
            return AgentResult(output="ok", success=True)

    runtime = Runtime(RecordingAgent(FakeProvider()))

    def callback(text: str) -> None:
        seen["callback_ran"] = True

    result = runtime.run("hi", on_delta=callback)

    assert seen["input_text"] == "hi"
    assert seen["on_delta"] is callback
    assert result.output == "ok"


def test_runtime_run_without_on_delta_keeps_plain_path():
    seen: dict[str, object] = {}

    class RecordingAgent(Agent):
        def run(self, input_text: str, *, on_delta=None):
            seen["on_delta"] = on_delta
            return _RESULT

    _RESULT = TextResponse("ok")
    runtime = Runtime(RecordingAgent(FakeProvider()))
    runtime.run("hi")

    assert seen["on_delta"] is None


def test_runtime_with_streaming_provider_streams_through_the_facade():
    provider = StreamingProvider(
        [[StreamTextDelta("Hel"), StreamTextDelta("lo"), TextResponse("Hello")]]
    )
    runtime = Runtime(Agent(provider))

    deltas: list[str] = []
    result = runtime.run("hi", on_delta=deltas.append)

    assert deltas == ["Hel", "lo"]
    assert result.output == "Hello"


def test_streaming_provider_signature_matches_provider_contract():
    """Streaming providers stay ordinary Provider implementations."""
    provider = StreamingProvider([[TextResponse("ok")]])
    assert isinstance(provider, Provider)
    assert isinstance(ProviderConfig(), ProviderConfig)


# --- Duck-typed provider fallbacks -------------------------------------------------


def test_agent_falls_back_when_provider_lacks_stream_response():
    """Duck-typed providers without stream_response() keep working with on_delta."""

    class OnlyGenerateResponse:
        def generate(self, prompt: str) -> str:
            return f"plain: {prompt}"

        def generate_response(self, prompt, *, tools=(), tool_results=()):
            return TextResponse(f"plain: {prompt}")

    deltas, result = collect_deltas(OnlyGenerateResponse())

    assert deltas == []
    assert result.success is True
    assert result.output == "plain: hi"
