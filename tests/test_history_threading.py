"""Native per-vendor history threading (ADR 0014).

The additive ``history`` keyword on the Provider contract: an Agent hands
remembered ``(role, text)`` pairs to providers that opt in via
``supports_native_history``, and each vendor adapter rehydrates them into
its native multi-message wire format. Providers that do not opt in keep
receiving the composed text prompt with exactly the pre-1.5 keyword set.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from nexusagent import Agent, AsyncAgent, InMemoryMemory, SQLiteMemory
from nexusagent.anthropic_provider import AnthropicProvider
from nexusagent.anthropic_provider import _messages_for as anthropic_messages_for
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.gemini_provider import GeminiProvider
from nexusagent.gemini_provider import _contents_for as gemini_contents_for
from nexusagent.http_provider import HttpProvider
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.openai_provider import _messages_for as openai_messages_for
from nexusagent.provider import (
    AsyncProvider,
    Provider,
    ProviderConfig,
    TextResponse,
    ToolCallRequest,
    ToolResult,
)
from nexusagent.providers import FakeProvider, ScriptedProvider

URLOPEN_TARGET = "nexusagent.http_provider.urllib.request.urlopen"

HISTORY: tuple[tuple[str, str], ...] = (
    ("user", "My name is Sara"),
    ("assistant", "Nice to meet you, Sara!"),
)


def make_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def make_openai() -> OpenAIProvider:
    return OpenAIProvider(ProviderConfig(model="test-model"))


def make_anthropic() -> AnthropicProvider:
    return AnthropicProvider(ProviderConfig(model="test-model"))


def make_gemini() -> GeminiProvider:
    return GeminiProvider(ProviderConfig(model="test-model"))


# --- Capability flags --------------------------------------------------


def test_providers_that_do_not_opt_in_default_to_false():
    assert Provider.supports_native_history is False
    assert AsyncProvider.supports_native_history is False
    assert FakeProvider().supports_native_history is False
    assert ScriptedProvider(responses=[TextResponse("x")]).supports_native_history is False
    assert HttpProvider().supports_native_history is False


def test_builtin_vendor_adapters_opt_in():
    assert OpenAIProvider().supports_native_history is True
    assert AnthropicProvider().supports_native_history is True
    assert GeminiProvider().supports_native_history is True


# --- Agent semantics ---------------------------------------------------


class RecordingProvider(FakeProvider):
    """FakeProvider that records every generate/stream call shape."""

    supports_native_history = True

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def generate_response(
        self,
        prompt: str,
        *,
        tools=(),
        tool_results=(),
        history=(),
    ):
        self.calls.append(
            {"prompt": prompt, "tools": tools, "tool_results": tool_results, "history": history}
        )
        return super().generate_response(
            prompt, tools=tools, tool_results=tool_results, history=history
        )

    def stream_response(self, prompt, *, tools=(), tool_results=(), history=()):
        self.calls.append(
            {
                "prompt": prompt,
                "tools": tools,
                "tool_results": tool_results,
                "history": history,
                "streamed": True,
            }
        )
        yield TextResponse(f"fake response: {prompt}")


def test_agent_passes_raw_input_and_history_to_native_provider():
    provider = RecordingProvider()
    memory = InMemoryMemory()
    agent = Agent(provider, memory=memory)

    agent.run("Hello")
    assert provider.calls[0] == {"prompt": "Hello", "tools": (), "tool_results": (), "history": ()}

    agent.run("Second")
    assert provider.calls[1]["prompt"] == "Second"
    assert provider.calls[1]["history"] == (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )
    # the composed transcript never leaks into the prompt of a native provider
    assert "Previous conversation" not in provider.calls[1]["prompt"]


def test_agent_passes_history_on_every_tool_loop_iteration():
    class ToolThenAnswer(FakeProvider):
        supports_native_history = True

        def __init__(self) -> None:
            super().__init__()
            self.prompts: list[tuple[str, tuple[tuple[str, str], ...]]] = []

        def generate_response(self, prompt, *, tools=(), tool_results=(), history=()):
            self.prompts.append((prompt, history))
            if tool_results:
                return TextResponse(f"done after {len(tool_results)} results")
            if prompt.strip() == "What is 2 + 3?":
                return ToolCallRequest("calculator", "2 + 3")
            return TextResponse(f"fake response: {prompt}")

    from nexusagent.tool_executor import ToolExecutor
    from nexusagent.tool_factory import create_tool_registry

    provider = ToolThenAnswer()
    agent = Agent(
        provider,
        tool_registry=create_tool_registry(),
        tool_executor=ToolExecutor(),
        memory=InMemoryMemory(),
    )
    agent.run("My name is Sara")
    agent.run("What is 2 + 3?")

    run1, iter1, iter2 = provider.prompts
    run1_expected = ("My name is Sara", ())
    run2_history = (
        ("user", "My name is Sara"),
        ("assistant", "fake response: My name is Sara"),
    )
    assert run1 == run1_expected
    assert iter1 == ("What is 2 + 3?", run2_history)
    # iteration 2 of the loop: same raw prompt, same history, plus the tool result
    assert iter2[0] == "What is 2 + 3?"
    assert iter2[1] == run2_history


def test_native_provider_without_memory_receives_empty_history():
    provider = RecordingProvider()
    agent = Agent(provider)

    result = agent.run("Hello")

    assert result.success is True
    assert provider.calls == [{"prompt": "Hello", "tools": (), "tool_results": (), "history": ()}]


def test_agent_still_composes_prompt_for_providers_without_the_kwarg():
    """A duck-typed provider predating 1.5 keeps its exact call shape."""

    class LegacyProvider:
        supports_native_history = False

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def generate(self, prompt: str) -> str:
            return f"legacy: {prompt}"

        def generate_response(self, prompt: str, *, tools=(), tool_results=()):
            self.prompts.append(prompt)
            return TextResponse(f"legacy: {prompt}")

    provider = LegacyProvider()
    agent = Agent(provider, memory=InMemoryMemory())  # type: ignore[arg-type]

    agent.run("Hello there")
    agent.run("Follow-up")

    assert provider.prompts[0] == "Hello there"
    assert provider.prompts[1].startswith("Previous conversation (oldest first):")
    assert "user: Hello there" in provider.prompts[1]
    assert provider.prompts[1].endswith("Respond to this new user message:\nFollow-up")


def test_agent_streaming_path_forwards_history_to_native_provider():
    provider = RecordingProvider()
    agent = Agent(provider, memory=InMemoryMemory())

    deltas: list[str] = []
    agent.run("Hello", on_delta=deltas.append)
    agent.run("Second", on_delta=deltas.append)

    assert provider.calls[0]["history"] == ()
    assert provider.calls[1]["prompt"] == "Second"
    assert provider.calls[1]["history"] == (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )
    assert provider.calls[1]["streamed"] is True


def test_history_threading_works_with_sqlite_memory():
    provider = RecordingProvider()
    memory = SQLiteMemory(":memory:")
    agent = Agent(provider, memory=memory)

    agent.run("Hello")
    agent.run("Second")

    assert provider.calls[1]["history"] == (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )
    memory.close()


def test_agent_result_composes_memory_identically_for_both_paths():
    """Recording (native) and FakeProvider (composed) end with the same memory."""

    native_memory = InMemoryMemory()
    Agent(RecordingProvider(), memory=native_memory).run("Hello")
    composed_memory = InMemoryMemory()
    Agent(FakeProvider(), memory=composed_memory).run("Hello")

    assert native_memory.history() == composed_memory.history()


# --- OpenAI wire -------------------------------------------------------


def test_openai_rehydrates_history_before_the_current_prompt():
    messages = openai_messages_for("What is my name?", (), history=HISTORY)

    assert messages == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "Nice to meet you, Sara!"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_openai_messages_without_history_are_unchanged():
    messages = openai_messages_for("hi there", ())

    assert messages == [{"role": "user", "content": "hi there"}]


@patch(URLOPEN_TARGET)
def test_openai_agent_end_to_end_sends_history_as_real_messages(mock_urlopen):
    payload = {"choices": [{"message": {"content": "Your name is Sara"}}]}
    mock_urlopen.return_value = make_response(payload)
    memory = InMemoryMemory()
    agent = Agent(make_openai(), memory=memory)

    agent.run("My name is Sara")
    agent.run("What is my name?")

    request = mock_urlopen.call_args.args[0]
    body = json.loads(request.data)
    assert body["messages"] == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "Your name is Sara"},
        {"role": "user", "content": "What is my name?"},
    ]


def make_sse_stream(events: list[str]) -> MagicMock:
    lines: list[bytes] = []
    for payload in events:
        lines.append(b"data: " + payload.encode("utf-8") + b"\n")
        lines.append(b"\n")
    response = MagicMock()
    response.__iter__.return_value = iter(lines)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def openai_chunk(delta: dict[str, object]) -> str:
    choice: dict[str, object] = {"index": 0, "delta": delta, "finish_reason": None}
    return json.dumps({"id": "c", "object": "chat.completion.chunk", "choices": [choice]})


@patch(URLOPEN_TARGET)
def test_openai_streaming_request_carries_history(mock_urlopen):
    stream_chunks = [
        openai_chunk({"role": "assistant", "content": ""}),
        openai_chunk({"content": "Your name is Sara"}),
        "[DONE]",
    ]
    # run 1 (non-streaming) consumes the chat.completion response;
    # run 2 (streaming, on_delta) consumes the SSE stream.
    mock_urlopen.side_effect = [
        make_response({"choices": [{"message": {"content": "Your name is Sara"}}]}),
        make_sse_stream(stream_chunks),
    ]
    memory = InMemoryMemory()
    agent = Agent(make_openai(), memory=memory)

    agent.run("My name is Sara")
    deltas: list[str] = []
    result = agent.run("What is my name?", on_delta=deltas.append)

    assert result.output == "Your name is Sara"
    request = mock_urlopen.call_args.args[0]
    body = json.loads(request.data)
    assert body["stream"] is True
    assert body["messages"][-1] == {"role": "user", "content": "What is my name?"}
    assert body["messages"][:2] == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "Your name is Sara"},
    ]


# --- Anthropic wire ----------------------------------------------------


def test_anthropic_rehydrates_history_before_the_current_prompt():
    messages = anthropic_messages_for("What is my name?", (), history=HISTORY)

    assert messages == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "Nice to meet you, Sara!"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_anthropic_merges_consecutive_same_role_turns():
    """The Messages wire demands alternation; custom backends may not deliver it."""

    messages = anthropic_messages_for(
        "hi", (), history=(("user", "a"), ("user", "b"), ("assistant", "c"))
    )

    assert messages == [
        {"role": "user", "content": "a\nb"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "hi"},
    ]


@patch(URLOPEN_TARGET)
def test_anthropic_agent_end_to_end_sends_history_as_real_turns(mock_urlopen):
    payload = {
        "content": [{"type": "text", "text": "Your name is Sara"}],
        "stop_reason": "end_turn",
    }
    mock_urlopen.return_value = make_response(payload)
    memory = InMemoryMemory()
    agent = Agent(make_anthropic(), memory=memory)

    agent.run("My name is Sara")
    agent.run("What is my name?")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["messages"] == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "Your name is Sara"},
        {"role": "user", "content": "What is my name?"},
    ]


# --- Gemini wire -------------------------------------------------------


def test_gemini_maps_assistant_turns_to_model_role():
    contents = gemini_contents_for("What is my name?", (), history=HISTORY)

    assert contents == [
        {"role": "user", "parts": [{"text": "My name is Sara"}]},
        {"role": "model", "parts": [{"text": "Nice to meet you, Sara!"}]},
        {"role": "user", "parts": [{"text": "What is my name?"}]},
    ]


def test_gemini_contents_without_history_are_unchanged():
    contents = gemini_contents_for("hi", ())

    assert contents == [{"role": "user", "parts": [{"text": "hi"}]}]


@patch(URLOPEN_TARGET)
def test_gemini_agent_end_to_end_sends_history_as_real_contents(mock_urlopen):
    payload = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": "Your name is Sara"}]}}]
    }
    mock_urlopen.return_value = make_response(payload)
    memory = InMemoryMemory()
    agent = Agent(make_gemini(), memory=memory)

    agent.run("My name is Sara")
    agent.run("What is my name?")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "My name is Sara"}]},
        {"role": "model", "parts": [{"text": "Your name is Sara"}]},
        {"role": "user", "parts": [{"text": "What is my name?"}]},
    ]


# --- HTTP provider keeps the composed transcript ------------------------


@patch(URLOPEN_TARGET)
def test_http_provider_keeps_composed_prompt_and_never_sends_history(mock_urlopen):
    """The vendor-neutral protocol is additive-frozen: bodies stay pre-1.5."""

    payload = {"output": "ok"}
    mock_urlopen.return_value = make_response(payload)
    memory = InMemoryMemory()
    provider = HttpProvider(ProviderConfig(endpoint="http://example.test/chat"))
    agent = Agent(provider, memory=memory)

    agent.run("Hello there")
    agent.run("Follow-up")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert "history" not in body
    assert "input" in body
    assert body["input"].startswith("Previous conversation (oldest first):")


# --- Async layer -------------------------------------------------------


class RecordingAsyncProvider(AsyncProvider):
    """Async provider that records every generate_response call shape."""

    supports_native_history = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str) -> str:
        return f"async fake response: {prompt}"

    async def generate_response(self, prompt, *, tools=(), tool_results=(), history=()):
        self.calls.append({"prompt": prompt, "history": history})
        return TextResponse(f"async fake response: {prompt}")


async def _run_async_agent(provider) -> None:  # type: ignore[no-untyped-def]
    memory = InMemoryMemory()
    agent = AsyncAgent(provider, memory=memory)
    await agent.run("Hello")
    await agent.run("Second")


def test_async_agent_passes_raw_input_and_history_to_native_provider():
    import asyncio

    provider = RecordingAsyncProvider()
    asyncio.run(_run_async_agent(provider))

    assert provider.calls[0] == {"prompt": "Hello", "history": ()}
    assert provider.calls[1] == {
        "prompt": "Second",
        "history": (("user", "Hello"), ("assistant", "async fake response: Hello")),
    }


async def _run_async_composed(provider) -> None:  # type: ignore[no-untyped-def]
    memory = InMemoryMemory()
    agent = AsyncAgent(provider, memory=memory)
    await agent.run("Hello")
    await agent.run("Second")


def test_async_agent_composes_prompt_for_providers_without_the_flag():
    import asyncio

    class LegacyAsync(AsyncProvider):
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def generate(self, prompt: str) -> str:
            return f"legacy: {prompt}"

        async def generate_response(self, prompt, *, tools=(), tool_results=()):
            self.prompts.append(prompt)
            return TextResponse(f"legacy: {prompt}")

    provider = LegacyAsync()
    asyncio.run(_run_async_composed(provider))  # type: ignore[arg-type]

    assert provider.prompts[0] == "Hello"
    assert provider.prompts[1].startswith("Previous conversation (oldest first):")


def test_sync_adapter_mirrors_the_wrapped_provider_flag():
    assert SyncProviderAdapter(OpenAIProvider()).supports_native_history is True
    assert SyncProviderAdapter(FakeProvider()).supports_native_history is False


def test_sync_adapter_forwards_history_only_to_opted_in_providers():
    import asyncio

    recorder = RecordingProvider()
    adapter = SyncProviderAdapter(recorder)
    memory = InMemoryMemory()

    async def scenario() -> None:
        agent = AsyncAgent(adapter, memory=memory)
        await agent.run("Hello")
        await agent.run("Second")

    asyncio.run(scenario())

    assert recorder.calls[1]["prompt"] == "Second"
    assert recorder.calls[1]["history"] == (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )


def test_sync_adapter_keeps_legacy_call_shape_for_unopted_providers():
    import asyncio

    class LegacyProvider:
        supports_native_history = False

        def __init__(self) -> None:
            self.seen: list[dict[str, Any]] = []

        def generate(self, prompt: str) -> str:
            return f"legacy: {prompt}"

        def generate_response(self, prompt: str, *, tools=(), tool_results=()):
            self.seen.append({"prompt": prompt})
            return TextResponse(f"legacy: {prompt}")

    provider = LegacyProvider()
    adapter = SyncProviderAdapter(provider)  # type: ignore[arg-type]

    async def scenario() -> None:
        agent = AsyncAgent(adapter, memory=InMemoryMemory())
        await agent.run("Hello")
        await agent.run("Second")

    asyncio.run(scenario())

    assert provider.seen[0]["prompt"] == "Hello"
    assert provider.seen[1]["prompt"].startswith("Previous conversation (oldest first):")


def test_async_provider_default_ignores_history_keyword():
    import asyncio

    class PlainAsync(AsyncProvider):
        async def generate(self, prompt: str) -> str:
            return f"plain: {prompt}"

    provider = PlainAsync()

    async def scenario() -> Any:
        return await provider.generate_response("hi", history=HISTORY)

    result = asyncio.run(scenario())
    assert result == TextResponse("plain: hi")


def test_streaming_agent_memory_path_uses_history_for_native_tool_loop():
    """Streaming + native history + tool loop: history reaches every iteration."""

    class StreamingNative(FakeProvider):
        supports_native_history = True

        def __init__(self) -> None:
            super().__init__()
            self.stream_calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []

        def stream_response(self, prompt, *, tools=(), tool_results=(), history=()):
            self.stream_calls.append((prompt, history))
            yield from super().stream_response(
                prompt, tools=tools, tool_results=tool_results, history=history
            )

    provider = StreamingNative()
    agent = Agent(provider, memory=InMemoryMemory())
    deltas: list[str] = []

    agent.run("Hello", on_delta=deltas.append)
    agent.run("Second", on_delta=deltas.append)

    run2_history = (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )
    assert provider.stream_calls[0] == ("Hello", ())
    assert provider.stream_calls[1] == ("Second", run2_history)


def test_tool_specs_and_results_still_reach_native_providers():
    """The pre-existing keywords are unchanged on the native path."""

    class RecordingWithTools(RecordingProvider):
        def generate_response(self, prompt, *, tools=(), tool_results=(), history=()):
            self.calls.append(
                {"prompt": prompt, "tools": tools, "tool_results": tool_results, "history": history}
            )
            if tool_results:
                return TextResponse("loop done")
            if prompt.strip() == "What is 2 + 3?":
                return ToolCallRequest("echo", "ping")
            return TextResponse(f"fake response: {prompt}")

    from nexusagent.tool_executor import ToolExecutor
    from nexusagent.tool_factory import create_tool_registry

    provider = RecordingWithTools()
    agent = Agent(
        provider,
        tool_registry=create_tool_registry(),
        tool_executor=ToolExecutor(),
        memory=InMemoryMemory(),
    )

    agent.run("My name is Sara")
    result = agent.run("What is 2 + 3?")

    assert result.success is True
    assert result.output == "loop done"
    iter1, iter2 = provider.calls[1], provider.calls[2]
    run2_history = (
        ("user", "My name is Sara"),
        ("assistant", "fake response: My name is Sara"),
    )
    assert [spec.name for spec in iter1["tools"]] == ["echo", "uppercase", "calculator"]
    assert iter1["tool_results"] == ()
    assert iter1["history"] == run2_history
    assert iter2["tool_results"] == (ToolResult("echo", "ping", "ping"),)
    assert iter2["history"] == run2_history


def test_async_streaming_forwards_history_through_the_adapter():
    """AsyncAgent streaming + adapter + native history: every layer forwards."""
    import asyncio

    recorder = RecordingProvider()
    adapter = SyncProviderAdapter(recorder)
    memory = InMemoryMemory()

    async def scenario() -> None:
        agent = AsyncAgent(adapter, memory=memory)
        deltas: list[str] = []
        await agent.run("Hello", on_delta=deltas.append)
        await agent.run("Second", on_delta=deltas.append)

    asyncio.run(scenario())

    assert recorder.calls[0]["history"] == ()
    assert recorder.calls[1]["prompt"] == "Second"
    assert recorder.calls[1]["history"] == (
        ("user", "Hello"),
        ("assistant", "fake response: Hello"),
    )


def test_async_adapter_generate_fallback_forwards_history():
    """Adapter without a wrapped stream falls back to generate_response(history)."""
    import asyncio

    class NativeNoStream(FakeProvider):
        supports_native_history = True

        def __init__(self) -> None:
            super().__init__()
            self.seen: list[tuple[str, tuple[tuple[str, str], ...]]] = []

        def generate_response(self, prompt, *, tools=(), tool_results=(), history=()):
            self.seen.append((prompt, history))
            return TextResponse(f"fake response: {prompt}")

    provider = NativeNoStream()
    adapter = SyncProviderAdapter(provider)

    async def scenario() -> None:
        agent = AsyncAgent(adapter, memory=InMemoryMemory())
        await agent.run("Hello", on_delta=lambda delta: None)
        await agent.run("Second", on_delta=lambda delta: None)

    asyncio.run(scenario())

    assert provider.seen[0] == ("Hello", ())
    assert provider.seen[1] == (
        "Second",
        (("user", "Hello"), ("assistant", "fake response: Hello")),
    )
