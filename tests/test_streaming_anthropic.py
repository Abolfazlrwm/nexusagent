"""Contract tests for AnthropicProvider.stream_response() (ADR 0009)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.anthropic_provider import DEFAULT_ENDPOINT, AnthropicProvider
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


def make_stream(events: list[str]) -> MagicMock:
    lines: list[bytes] = []
    for payload in events:
        lines.append(b"data: " + payload.encode("utf-8") + b"\n")
        lines.append(b"\n")
    response = MagicMock()
    response.__iter__.return_value = iter(lines)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def event(payload: dict) -> str:
    return json.dumps(payload)


def text_delta(index: int, text: str) -> str:
    return event(
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "text_delta", "text": text},
        }
    )


def input_json_delta(index: int, partial: str) -> str:
    return event(
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {"type": "input_json_delta", "partial_json": partial},
        }
    )


def text_stream_events(text_fragments: list[str]) -> list[str]:
    events = [event({"type": "message_start", "message": {"id": "m"}})]
    events.append(
        event({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}})
    )
    for fragment in text_fragments:
        events.append(text_delta(0, fragment))
    events.append(event({"type": "content_block_stop", "index": 0}))
    events.append(event({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}))
    events.append(event({"type": "message_stop"}))
    return events


def make_provider(**config_kwargs: object) -> AnthropicProvider:
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return AnthropicProvider(ProviderConfig(**kwargs))  # type: ignore[arg-type]


# --- Text streaming -------------------------------------------------------------


def test_stream_yields_deltas_then_final_text_response():
    events = text_stream_events(["Hello", " world"])
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [
        StreamTextDelta("Hello"),
        StreamTextDelta(" world"),
        TextResponse("Hello world"),
    ]


def test_stream_request_body_carries_stream_true_model_and_max_tokens():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider().stream_response("hi"))

    body = captured["body"]
    assert body["stream"] is True
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 1024
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_stream_sends_anthropic_version_and_api_key_headers():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider(api_key="secret-key").stream_response("hi"))

    assert captured["headers"]["Anthropic-version"] == "2023-06-01"
    assert captured["headers"]["X-api-key"] == "secret-key"


def test_stream_targets_the_default_endpoint():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.get_full_url()
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider().stream_response("hi"))

    assert captured["url"] == DEFAULT_ENDPOINT


def test_stream_advertises_tools_and_rehydrates_tool_results():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream([])

    tools = (ToolSpec("calculator", "Arithmetic."),)
    results = (ToolResult("calculator", "2+3", "5"),)
    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider().stream_response("hi", tools=tools, tool_results=results))

    body = captured["body"]
    assert body["tools"][0]["name"] == "calculator"
    assert body["messages"][1]["content"][0]["type"] == "tool_use"
    assert body["messages"][2]["content"][0]["type"] == "tool_result"


def test_stream_config_validation_is_eager():
    provider = AnthropicProvider(ProviderConfig())
    with (
        patch(URLOPEN_TARGET) as urlopen,
        pytest.raises(ProviderConfigurationError, match="model"),
    ):
        provider.stream_response("hi")

    urlopen.assert_not_called()


# --- Tool call streaming ---------------------------------------------------------


def tool_use_stream_events(name: str, fragments: list[str], index: int = 1) -> list[str]:
    events = [event({"type": "message_start", "message": {"id": "m"}})]
    events.append(
        event({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}})
    )
    events.append(text_delta(0, "Let me calculate."))
    events.append(event({"type": "content_block_stop", "index": 0}))
    events.append(
        event(
            {
                "type": "content_block_start",
                "index": index,
                "content_block": {"type": "tool_use", "id": "toolu_1", "name": name},
            }
        )
    )
    for fragment in fragments:
        events.append(input_json_delta(index, fragment))
    events.append(event({"type": "content_block_stop", "index": index}))
    events.append(event({"type": "message_delta", "delta": {"stop_reason": "tool_use"}}))
    events.append(event({"type": "message_stop"}))
    return events


def test_stream_accumulates_input_json_fragments_into_tool_request():
    events = tool_use_stream_events("calculator", ['{"input"', ': "2 + 3"}'])
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[:2] == [
        StreamTextDelta("Let me calculate."),
        ToolCallRequest("calculator", "2 + 3"),
    ]


def test_stream_tool_call_without_input_fragments_reports_missing_input():
    events = tool_use_stream_events("calculator", [])
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="input"),
    ):
        list(provider.stream_response("hi"))


def test_stream_ignores_input_json_fragments_of_other_blocks():
    events = tool_use_stream_events("calculator", ['{"input": "1"}'])
    events.append(input_json_delta(9, '{"unrelated": true}'))
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[-1] == ToolCallRequest("calculator", "1")


def test_stream_consumes_only_the_first_tool_use_block():
    events = tool_use_stream_events("calculator", ['{"input": "1"}'], index=1)
    events.append(
        event(
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {"type": "tool_use", "id": "toolu_2", "name": "echo"},
            }
        )
    )
    events.append(input_json_delta(2, '{"input": "2"}'))
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[-1] == ToolCallRequest("calculator", "1")


def test_stream_invalid_tool_input_json_raises():
    events = tool_use_stream_events("calculator", ["{oops"])
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="not valid JSON"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_object_tool_input_raises():
    events = tool_use_stream_events("calculator", ["[1]"])
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="'input' object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_tool_use_without_name_raises():
    events = [
        event(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "toolu_1"},
            }
        ),
        event({"type": "message_stop"}),
    ]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="name"),
    ):
        list(provider.stream_response("hi"))


def test_stream_accepts_lenient_single_parameter_name():
    events = tool_use_stream_events("calculator", ['{"query": "2+3"}'])
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[-1] == ToolCallRequest("calculator", "2+3")


# --- Robustness ------------------------------------------------------------------


def test_stream_ignores_ping_and_thinking_deltas():
    events = text_stream_events(["Hello"])
    events.insert(2, event({"type": "ping"}))
    events.append(
        event(
            {
                "type": "content_block_delta",
                "index": 5,
                "delta": {"type": "thinking_delta", "thinking": "hmm"},
            }
        )
    )
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_error_event_raises_provider_response_error():
    events = [event({"type": "error", "error": {"type": "overloaded", "message": "slow down"}})]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="slow down"),
    ):
        list(provider.stream_response("hi"))


def test_stream_malformed_json_event_raises():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(["{oops"])),
        pytest.raises(ProviderResponseError, match="not valid JSON"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_object_event_raises():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(["42"])),
        pytest.raises(ProviderResponseError, match="JSON object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_string_text_delta_raises():
    events = [text_delta(0, 42)]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="string 'text'"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_string_partial_json_raises():
    events = [
        event(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "t", "name": "calc"},
            }
        ),
        input_json_delta(0, 42),
    ]
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="partial_json"),
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
    events = text_stream_events(["   "])
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="ended without"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_streaming_path_still_works_alongside():
    payload = {"content": [{"type": "text", "text": "plain answer"}]}
    raw = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=response):
        assert provider.generate_response("hi") == TextResponse("plain answer")


# --- Edge cases for full branch coverage -----------------------------------------


def test_stream_error_event_with_non_object_error_payload():
    provider = make_provider()
    with (
        patch(
            URLOPEN_TARGET, return_value=make_stream([event({"type": "error", "error": "boom"})])
        ),
        pytest.raises(ProviderResponseError, match="boom"),
    ):
        list(provider.stream_response("hi"))


def test_stream_skips_delta_events_whose_delta_is_not_an_object():
    events = text_stream_events(["Hello"])
    events.append(event({"type": "content_block_delta", "index": 0, "delta": "not an object"}))
    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]
