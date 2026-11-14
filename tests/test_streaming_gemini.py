"""Contract tests for GeminiProvider.stream_response() (ADR 0009)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.gemini_provider import GeminiProvider
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


def text_chunk(text: str) -> str:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]})


def function_call_chunk(name: str, args: dict) -> str:
    return json.dumps(
        {"candidates": [{"content": {"parts": [{"functionCall": {"name": name, "args": args}}]}}]}
    )


def usage_chunk() -> str:
    return json.dumps({"usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}})


def make_provider(**config_kwargs: object) -> GeminiProvider:
    max_tokens = config_kwargs.pop("max_tokens", None)
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return GeminiProvider(
        ProviderConfig(**kwargs),  # type: ignore[arg-type]
        max_tokens=max_tokens,  # type: ignore[arg-type]
    )


# --- Text streaming -------------------------------------------------------------


def test_stream_yields_deltas_then_final_text_response():
    provider = make_provider()
    events = [text_chunk("Hello"), text_chunk(" world")]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [
        StreamTextDelta("Hello"),
        StreamTextDelta(" world"),
        TextResponse("Hello world"),
    ]


def test_stream_targets_stream_generate_content_with_sse():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.get_full_url()
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider().stream_response("hi"))

    assert (
        captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/test-model"
        ":streamGenerateContent?alt=sse"
    )


def test_stream_uses_endpoint_override_as_base_url():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.get_full_url()
        return make_stream([])

    base = "http://gw.test:8000"
    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider(endpoint=base).stream_response("hi"))

    assert (
        captured["url"]
        == "http://gw.test:8000/v1beta/models/test-model:streamGenerateContent?alt=sse"
    )


def test_stream_request_body_carries_contents():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider().stream_response("hi"))

    body = captured["body"]
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert "generationConfig" not in body


def test_stream_sends_max_tokens_as_generation_config():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider(max_tokens=256).stream_response("hi"))

    assert captured["body"]["generationConfig"] == {"maxOutputTokens": 256}


def test_stream_sends_api_key_header_when_set():
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen), pytest.raises(ProviderResponseError):
        list(make_provider(api_key="secret-key").stream_response("hi"))

    assert captured["headers"]["X-goog-api-key"] == "secret-key"


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
    assert body["contents"][1]["role"] == "model"
    assert body["contents"][1]["parts"][0]["functionCall"]["name"] == "calculator"
    assert body["contents"][2]["parts"][0]["functionResponse"]["response"] == {"result": "5"}


def test_stream_config_validation_is_eager():
    provider = GeminiProvider(ProviderConfig())
    with (
        patch(URLOPEN_TARGET) as urlopen,
        pytest.raises(ProviderConfigurationError, match="model"),
    ):
        provider.stream_response("hi")

    urlopen.assert_not_called()


# --- Tool call streaming ---------------------------------------------------------


def test_stream_function_call_chunk_becomes_tool_request():
    provider = make_provider()
    events = [function_call_chunk("calculator", {"input": "2 + 3"})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calculator", "2 + 3")]


def test_stream_tool_call_wins_over_streamed_text():
    provider = make_provider()
    events = [text_chunk("Calculating..."), function_call_chunk("calc", {"input": "1"})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out[0] == StreamTextDelta("Calculating...")
    assert events_out[-1] == ToolCallRequest("calc", "1")


def test_stream_consumes_only_the_first_function_call():
    provider = make_provider()
    events = [
        function_call_chunk("calc", {"input": "1"}),
        function_call_chunk("echo", {"input": "2"}),
    ]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calc", "1")]


def test_stream_accepts_lenient_single_parameter_name():
    provider = make_provider()
    events = [function_call_chunk("calc", {"query": "2+3"})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [ToolCallRequest("calc", "2+3")]


def test_stream_function_call_without_name_raises():
    provider = make_provider()
    events = [
        json.dumps({"candidates": [{"content": {"parts": [{"functionCall": {"args": {}}}]}}]})
    ]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="name"),
    ):
        list(provider.stream_response("hi"))


def test_stream_function_call_without_args_raises():
    provider = make_provider()
    events = [
        json.dumps({"candidates": [{"content": {"parts": [{"functionCall": {"name": "calc"}}]}}]})
    ]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="args"),
    ):
        list(provider.stream_response("hi"))


# --- Robustness ------------------------------------------------------------------


def test_stream_skips_usage_only_chunks():
    provider = make_provider()
    events = [usage_chunk(), text_chunk("Hello"), usage_chunk()]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_error_object_raises_provider_response_error():
    provider = make_provider()
    events = [json.dumps({"error": {"code": 429, "message": "quota exceeded"}})]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="quota exceeded"),
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
        patch(URLOPEN_TARGET, return_value=make_stream(["[1]"])),
        pytest.raises(ProviderResponseError, match="JSON object"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_string_text_part_raises():
    provider = make_provider()
    events = [json.dumps({"candidates": [{"content": {"parts": [{"text": 42}]}}]})]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="string 'text'"),
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
    provider = make_provider()
    events = [text_chunk("  ")]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="ended without"),
    ):
        list(provider.stream_response("hi"))


def test_stream_non_streaming_path_still_works_alongside():
    payload = {"candidates": [{"content": {"parts": [{"text": "plain answer"}]}}]}
    raw = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__.return_value = response
    response.__exit__.return_value = False

    provider = make_provider()
    with patch(URLOPEN_TARGET, return_value=response):
        assert provider.generate_response("hi") == TextResponse("plain answer")


# --- Edge cases for full branch coverage -----------------------------------------


def test_stream_error_with_non_object_error_payload():
    provider = make_provider()
    with (
        patch(URLOPEN_TARGET, return_value=make_stream([json.dumps({"error": "boom"})])),
        pytest.raises(ProviderResponseError, match="boom"),
    ):
        list(provider.stream_response("hi"))


def test_stream_skips_chunks_whose_candidate_is_not_an_object():
    provider = make_provider()
    events = [text_chunk("Hello"), json.dumps({"candidates": ["not an object"]})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_skips_chunks_whose_content_is_not_an_object():
    provider = make_provider()
    events = [text_chunk("Hello"), json.dumps({"candidates": [{"content": "nope"}]})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_skips_chunks_whose_parts_are_not_a_list():
    provider = make_provider()
    events = [text_chunk("Hello"), json.dumps({"candidates": [{"content": {"parts": "nope"}}]})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_skips_non_object_parts():
    provider = make_provider()
    events = [text_chunk("Hello"), json.dumps({"candidates": [{"content": {"parts": ["x"]}}]})]
    with patch(URLOPEN_TARGET, return_value=make_stream(events)):
        events_out = list(provider.stream_response("hi"))

    assert events_out == [StreamTextDelta("Hello"), TextResponse("Hello")]


def test_stream_function_call_part_that_is_not_an_object_raises():
    provider = make_provider()
    events = [json.dumps({"candidates": [{"content": {"parts": [{"functionCall": "x"}]}}]})]
    with (
        patch(URLOPEN_TARGET, return_value=make_stream(events)),
        pytest.raises(ProviderResponseError, match="object"),
    ):
        list(provider.stream_response("hi"))
