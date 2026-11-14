"""Contract tests for OpenAIProvider.stream_response() (ADR 0009)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.openai_provider import DEFAULT_ENDPOINT, OpenAIProvider
from nexusagent.provider import (
    ProviderConfig,
    ProviderConfigurationError,
    ProviderResponseError,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

URLOPEN_TARGET = "nexusagent.http_provider.urllib.request.urlopen"

DONE = "[DONE]"


def make_stream(events: list[str]) -> MagicMock:
    """Build an open SSE HTTP response from data payload strings."""
    lines: list[bytes] = []
    for payload in events:
        lines.append(b"data: " + payload.encode("utf-8") + b"\n")
        lines.append(b"\n")
    response = MagicMock()
    response.__iter__.return_value = iter(lines)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def chunk(**delta: object) -> str:
    """Encode one chat.completion.chunk SSE payload from its delta fields."""
    choice: dict[str, object] = {"index": 0, "delta": delta, "finish_reason": None}
    return json.dumps({"id": "c", "object": "chat.completion.chunk", "choices": [choice]})


def role_chunk() -> str:
    return chunk(role="assistant", content="")


def content_chunk(text: str) -> str:
    return chunk(content=text)


def tool_chunk(name: str | None = None, arguments: str | None = None) -> str:
    function: dict[str, str] = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    fragment: dict[str, object] = {"index": 0, "type": "function", "function": function}
    return chunk(tool_calls=[fragment])


def make_provider(**config_kwargs: object) -> OpenAIProvider:
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return OpenAIProvider(ProviderConfig(**kwargs))  # type: ignore[arg-type]


def capture_request(**config_kwargs: object):
    """Run a streaming call and return (events, captured request)."""
    captured: dict[str, object] = {}
    events_list: list[str] = []

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.get_full_url()
        captured["method"] = request.get_method()
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream(events_list)

    return captured, events_list, fake_urlopen


# --- Text streaming -------------------------------------------------------------


def test_stream_yields_deltas_then_final_text_response():
    events = [role_chunk(), content_chunk("Hello"), content_chunk(" world"), DONE]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [
        StreamTextDelta("Hello"),
        StreamTextDelta(" world"),
        TextResponse("Hello world"),
    ]


def test_stream_request_body_carries_stream_true_and_model():
    captured, events, fake = capture_request()
    events.append(content_chunk("hi"))
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(make_provider().stream_response("hi"))

    body = captured["body"]
    assert body["stream"] is True
    assert body["model"] == "test-model"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_stream_targets_the_default_endpoint():
    captured, events, fake = capture_request()
    events.append(content_chunk("hi"))
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(make_provider().stream_response("hi"))

    assert captured["url"] == DEFAULT_ENDPOINT


def test_stream_uses_endpoint_override():
    captured, events, fake = capture_request(endpoint="http://localhost:11434/v1/chat/completions")
    events.append(content_chunk("hi"))
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(
            make_provider(endpoint="http://localhost:11434/v1/chat/completions").stream_response(
                "hi"
            )
        )

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"


def test_stream_sends_authorization_header_when_api_key_set():
    captured, events, fake = capture_request(api_key="secret-key")
    events.append(content_chunk("hi"))
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(make_provider(api_key="secret-key").stream_response("hi"))

    assert captured["headers"]["Authorization"] == "Bearer secret-key"


def test_stream_advertises_tools_in_request_body():
    captured, events, fake = capture_request()
    events.append(content_chunk("hi"))
    tools = (ToolSpec("calculator", "Arithmetic."),)
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(make_provider().stream_response("hi", tools=tools))

    wire_tools = captured["body"]["tools"]
    assert wire_tools[0]["type"] == "function"
    assert wire_tools[0]["function"]["name"] == "calculator"


def test_stream_rehydrates_tool_results_into_messages():
    captured, events, fake = capture_request()
    events.append(content_chunk("done"))
    results = (ToolResult("calculator", "2+3", "5"),)
    with patch(URLOPEN_TARGET, side_effect=fake):
        list(make_provider().stream_response("hi", tool_results=results))

    messages = captured["body"]["messages"]
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "tool"
    assert messages[2]["content"] == "5"


def test_stream_config_validation_is_eager():
    provider = OpenAIProvider(ProviderConfig())
    with (
        patch(URLOPEN_TARGET) as urlopen,
        pytest.raises(ProviderConfigurationError, match="model"),
    ):
        provider.stream_response("hi")

    urlopen.assert_not_called()


# --- Tool call streaming ---------------------------------------------------------


def test_stream_accumulates_tool_call_fragments_into_request():
    events = [
        role_chunk(),
        tool_chunk(name="calculator", arguments=""),
        tool_chunk(arguments='{"input"'),
        tool_chunk(arguments=': "2 + 3"}'),
        chunk(),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calculator", "2 + 3")]


def test_stream_tool_call_yields_no_text_deltas():
    events = [tool_chunk(name="calculator", arguments='{"input": "1"}'), DONE]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert all(not isinstance(event, StreamTextDelta) for event in events_out)


def test_stream_prefers_the_first_tool_call_index():
    events = [tool_chunk(name="calculator", arguments='{"input": "1"}'), DONE]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calculator", "1")]


def test_stream_ignores_additional_parallel_tool_calls():
    events = [
        role_chunk(),
        tool_chunk(name="calculator", arguments='{"input": "1"}'),
        chunk(
            tool_calls=[
                {"index": 1, "type": "function", "function": {"name": "echo", "arguments": "{}"}}
            ]
        ),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calculator", "1")]


def test_stream_tool_call_wins_over_streamed_text():
    events = [
        content_chunk("Calculating..."),
        tool_chunk(name="calculator", arguments='{"input": "1"}'),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[0] == StreamTextDelta("Calculating...")
    assert events_out[-1] == ToolCallRequest("calculator", "1")


def test_stream_empty_tool_arguments_reports_missing_input():
    events = [tool_chunk(name="calculator", arguments=""), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="input"),
    ):
        list(provider.stream_response("hi"))


def test_stream_invalid_accumulated_arguments_raise():
    events = [tool_chunk(name="calculator", arguments="{oops"), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="not valid JSON"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_object_arguments_raise():
    events = [tool_chunk(name="calculator", arguments="[1, 2]"), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="JSON object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_tool_call_without_name_raises():
    events = [tool_chunk(arguments='{"input": "1"}'), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="name"),
    ):
        list(provider.stream_response("hi"))


def test_stream_tool_call_without_function_raises():
    events = [chunk(tool_calls=[{"index": 0}]), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="function"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_string_tool_arguments_raise():
    events = [chunk(tool_calls=[{"index": 0, "function": {"arguments": 42}}]), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="arguments"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_list_tool_calls_raise():
    events = [chunk(tool_calls="nope"), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="list"),
    ):
        list(provider.stream_response("hi"))


def test_stream_accepts_lenient_single_parameter_name():
    events = [
        chunk(
            tool_calls=[{"index": 0, "function": {"name": "calc", "arguments": '{"query": "2+3"}'}}]
        ),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calc", "2+3")]


# --- Robustness ------------------------------------------------------------------


def test_stream_done_terminates_and_ignores_later_events():
    events = [content_chunk("Hello"), DONE, content_chunk(" ignored")]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_skips_keep_alive_chunks_without_choices():
    events = [
        content_chunk("Hello"),
        json.dumps({"id": "c", "object": "chat.completion.chunk", "choices": []}),
        json.dumps({"id": "c", "object": "chat.completion.chunk"}),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_ignores_non_string_content_deltas():
    events = [content_chunk("Hello"), chunk(content=42), DONE]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_error_chunk_raises_provider_response_error():
    events = [json.dumps({"error": {"message": "rate limited", "type": "429"}})]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="rate limited"),
    ):
        list(provider.stream_response("hi"))


def test_stream_malformed_json_event_raises():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(["not json {"])),
        pytest.raises(ProviderResponseError, match="not valid JSON"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_object_event_raises():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(["[1, 2]"])),
        pytest.raises(ProviderResponseError, match="JSON object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_empty_stream_raises():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream([])),
        pytest.raises(ProviderResponseError, match="ended without"),
    ):
        list(provider.stream_response("hi"))


def test_stream_whitespace_only_text_raises():
    events = [content_chunk("   "), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="ended without"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_streaming_path_still_works_alongside():
    payload = {"choices": [{"message": {"content": "plain answer"}}]}
    raw = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=response):
        assert provider.generate_response("hi") == TextResponse("plain answer")


# --- Edge cases for full branch coverage -----------------------------------------


def test_stream_error_chunk_with_non_object_error_payload():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream([json.dumps({"error": "boom"})])),
        pytest.raises(ProviderResponseError, match="boom"),
    ):
        list(provider.stream_response("hi"))


def test_stream_skips_chunks_whose_choice_is_not_an_object():
    events = [
        content_chunk("Hello"),
        json.dumps({"choices": ["not an object"]}),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_skips_chunks_whose_delta_is_not_an_object():
    events = [
        content_chunk("Hello"),
        json.dumps({"choices": [{"index": 0, "delta": "not an object"}]}),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_non_object_tool_call_fragment_raises():
    events = [chunk(tool_calls=["not an object"]), DONE]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="must be an object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_tool_call_fragment_without_index_is_accepted():
    events = [
        chunk(tool_calls=[{"function": {"name": "calc", "arguments": '{"input": "1"}'}}]),
        DONE,
    ]
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calc", "1")]
