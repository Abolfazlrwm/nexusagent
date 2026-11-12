import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.gemini_provider import (
    DEFAULT_ENDPOINT,
    GeminiProvider,
)
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

URLOPEN_TARGET = "nexusagent.http_provider.urllib.request.urlopen"


def make_response(payload: object, raw: bytes | None = None) -> MagicMock:
    response = MagicMock()
    response.read.return_value = raw if raw is not None else json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def make_raw_response(raw: bytes) -> MagicMock:
    return make_response(None, raw=raw)


def generate_content_response(
    parts: list[object] | None = None,
    extra_parts: list[object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Build a minimal Gemini generateContent response payload."""
    content_parts: list[object] = []
    content_parts.extend(extra_parts or [])
    if parts:
        content_parts.extend(parts)

    candidate: dict[str, object] = {
        "content": {"role": "model", "parts": content_parts},
        "finishReason": "STOP",
    }
    payload: dict[str, object] = {"candidates": [candidate]}
    payload.update(overrides)
    return payload


def text_part(text: object) -> dict[str, object]:
    return {"text": text}


def make_function_call(
    name: str = "calculator",
    args: object = {"input": "2 + 3"},
) -> dict[str, object]:
    return {"functionCall": {"name": name, "args": args}}


def make_provider(**config_kwargs: object) -> GeminiProvider:
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return GeminiProvider(ProviderConfig(**kwargs))  # type: ignore[arg-type]


# --- Construction and identity -------------------------------------------------


def test_gemini_provider_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("constructing GeminiProvider must not connect")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    GeminiProvider(ProviderConfig(model="test-model"))


def test_gemini_provider_is_a_provider():
    assert isinstance(make_provider(), Provider)


def test_gemini_provider_defaults_to_no_config():
    provider = GeminiProvider()

    assert provider.config == ProviderConfig()
    assert provider.max_tokens is None


def test_gemini_provider_accepts_explicit_max_tokens():
    provider = GeminiProvider(max_tokens=512)

    assert provider.max_tokens == 512


# --- Configuration validation --------------------------------------------------


def test_gemini_provider_missing_model_raises():
    provider = GeminiProvider(ProviderConfig())

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


def test_gemini_provider_whitespace_only_model_raises():
    provider = make_provider(model="   ")

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_gemini_provider_invalid_timeout_raises(timeout):
    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError, match="timeout"):
        provider.generate("hi")


@pytest.mark.parametrize("max_tokens", [0, -1, 1.5, "1024", True])
def test_gemini_provider_invalid_max_tokens_raises(max_tokens):
    provider = GeminiProvider(ProviderConfig(model="test-model"), max_tokens=max_tokens)

    with pytest.raises(ProviderConfigurationError, match="max_tokens"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_gemini_provider_invalid_timeout_does_not_perform_network_access(monkeypatch, timeout):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid timeout must not trigger a network request")

    monkeypatch.setattr(URLOPEN_TARGET, fail_if_called)

    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


def test_gemini_provider_invalid_max_tokens_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid max_tokens must not trigger a network request")

    monkeypatch.setattr(URLOPEN_TARGET, fail_if_called)

    provider = GeminiProvider(ProviderConfig(model="test-model"), max_tokens=0)

    with pytest.raises(ProviderConfigurationError, match="max_tokens"):
        provider.generate("hi")


# --- Request shape -------------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_gemini_provider_sends_expected_request(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    config = ProviderConfig(
        model="test-model",
        api_key="secret-key",
        endpoint="https://example.test",
        timeout=5,
    )
    provider = GeminiProvider(config)

    provider.generate("hi there")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://example.test/v1beta/models/test-model:generateContent"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-goog-api-key") == "secret-key"

    body = json.loads(request.data)
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi there"}]}]
    assert "generationConfig" not in body

    assert mock_urlopen.call_args.kwargs["timeout"] == 5


@patch(URLOPEN_TARGET)
def test_gemini_provider_uses_default_endpoint_without_configuration(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == f"{DEFAULT_ENDPOINT}/v1beta/models/test-model:generateContent"
    assert mock_urlopen.call_args.kwargs["timeout"] == 30.0


@patch(URLOPEN_TARGET)
def test_gemini_provider_supports_gateways_via_endpoint_override(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider(endpoint="http://localhost:8080/gemini/")

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert (
        request.full_url == "http://localhost:8080/gemini/v1beta/models/test-model:generateContent"
    )


@patch(URLOPEN_TARGET)
def test_gemini_provider_without_api_key_omits_auth_header(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider(api_key=None)

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.get_header("X-goog-api-key") is None


@patch(URLOPEN_TARGET)
def test_gemini_provider_sends_configured_max_tokens(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = GeminiProvider(ProviderConfig(model="test-model"), max_tokens=256)

    provider.generate("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["generationConfig"] == {"maxOutputTokens": 256}


@patch(URLOPEN_TARGET)
def test_gemini_provider_advertises_tools_with_input_schema(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response(
        "hi",
        tools=(ToolSpec("calculator", "Performs basic arithmetic operations."),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["tools"] == [
        {
            "name": "calculator",
            "description": "Performs basic arithmetic operations.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "input": {
                        "type": "STRING",
                        "description": "Raw text input for the tool.",
                    }
                },
                "required": ["input"],
            },
        }
    ]


@patch(URLOPEN_TARGET)
def test_gemini_provider_omits_tools_key_without_tools(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert "tools" not in body


# --- Stateless tool-result rehydration -----------------------------------------


@patch(URLOPEN_TARGET)
def test_gemini_provider_rehydrates_one_tool_result(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response(
        "What is 2 + 3?",
        tool_results=(ToolResult("calculator", "2 + 3", "5"),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "What is 2 + 3?"}]},
        {
            "role": "model",
            "parts": [{"functionCall": {"name": "calculator", "args": {"input": "2 + 3"}}}],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "calculator",
                        "response": {"result": "5"},
                    }
                }
            ],
        },
    ]


@patch(URLOPEN_TARGET)
def test_gemini_provider_rehydrates_several_tool_results_in_order(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response(
        "do two things",
        tool_results=(
            ToolResult("echo", "first", "first echoed"),
            ToolResult("calculator", "2 + 3", "5"),
        ),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    roles = [turn["role"] for turn in body["contents"]]
    assert roles == ["user", "model", "user", "model", "user"]
    assert body["contents"][1]["parts"][0]["functionCall"]["name"] == "echo"
    assert body["contents"][2]["parts"][0]["functionResponse"]["name"] == "echo"
    assert body["contents"][2]["parts"][0]["functionResponse"]["response"] == {
        "result": "first echoed"
    }
    assert body["contents"][3]["parts"][0]["functionCall"]["name"] == "calculator"
    assert body["contents"][4]["parts"][0]["functionResponse"]["name"] == "calculator"
    assert body["contents"][4]["parts"][0]["functionResponse"]["response"] == {"result": "5"}


@patch(URLOPEN_TARGET)
def test_gemini_provider_marks_error_tool_results_with_error_object(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response(
        "hi",
        tool_results=(ToolResult("calculator", "nonsense", "invalid expression", is_error=True),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    function_response = body["contents"][-1]["parts"][0]["functionResponse"]
    assert function_response["response"] == {"error": "invalid expression"}


@patch(URLOPEN_TARGET)
def test_gemini_provider_successful_tool_results_carry_no_error_key(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello")]))
    provider = make_provider()

    provider.generate_response("hi", tool_results=(ToolResult("echo", "hi", "hi echoed"),))

    body = json.loads(mock_urlopen.call_args.args[0].data)
    response_object = body["contents"][-1]["parts"][0]["functionResponse"]["response"]
    assert "error" not in response_object


# --- Text response parsing ------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_gemini_provider_returns_text_content(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("hello world")]))
    provider = make_provider()

    assert provider.generate("hi") == "hello world"


@patch(URLOPEN_TARGET)
def test_gemini_provider_preserves_surrounding_whitespace_in_text(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part(" hello ")]))
    provider = make_provider()

    assert provider.generate("hi") == " hello "


@patch(URLOPEN_TARGET)
def test_gemini_provider_joins_multiple_text_parts(mock_urlopen):
    mock_urlopen.return_value = make_response(
        generate_content_response([text_part("hello "), text_part("world")])
    )
    provider = make_provider()

    assert provider.generate("hi") == "hello world"


@patch(URLOPEN_TARGET)
def test_gemini_provider_generate_response_returns_text_response(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([text_part("answer")]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == TextResponse("answer")


@patch(URLOPEN_TARGET)
def test_gemini_provider_skips_unknown_content_part_types(mock_urlopen):
    mock_urlopen.return_value = make_response(
        generate_content_response([text_part("answer")], extra_parts=[{"inlineData": {}}])
    )
    provider = make_provider()

    assert provider.generate("hi") == "answer"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"no_candidates": True},
        {"candidates": []},
        {"candidates": "not-a-list"},
        {"candidates": ["not-a-dict"]},
        {"candidates": [{"finishReason": "STOP"}]},
        {"candidates": [{"content": {}}]},
        {"candidates": [{"content": {"parts": []}}]},
        {"candidates": [{"content": {"parts": "not-a-list"}}]},
        {"candidates": [{"content": {"parts": ["not-a-dict"]}}]},
        {"candidates": [{"content": {"parts": [42]}}]},
        {"candidates": [{"content": {"parts": [{"text": 123}]}}]},
        {"candidates": [{"content": {"parts": [{"unknownPart": 1}]}}]},
    ],
)
@patch(URLOPEN_TARGET)
def test_gemini_provider_malformed_payloads_raise(mock_urlopen, payload):
    mock_urlopen.return_value = make_response(payload)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"text"', b"42"])
@patch(URLOPEN_TARGET)
def test_gemini_provider_invalid_json_raises(mock_urlopen, raw):
    mock_urlopen.return_value = make_raw_response(raw)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- Tool call parsing -----------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_gemini_provider_parses_function_call_with_input_key(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([make_function_call()]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_gemini_provider_accepts_models_that_pick_their_own_parameter_name(mock_urlopen):
    call = make_function_call(name="calculator", args={"expression": "2 + 3"})
    mock_urlopen.return_value = make_response(generate_content_response([call]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_gemini_provider_uses_first_of_several_function_calls(mock_urlopen):
    calls = [make_function_call(name="echo"), make_function_call(name="uppercase")]
    mock_urlopen.return_value = make_response(generate_content_response(calls))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)
    assert response.tool_name == "echo"


@patch(URLOPEN_TARGET)
def test_gemini_provider_prefers_function_call_over_text(mock_urlopen):
    mock_urlopen.return_value = make_response(
        generate_content_response([text_part("some text"), make_function_call()])
    )
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)


@pytest.mark.parametrize(
    "parts",
    [
        [42],
        [{"functionCall": 42}],
        [{"functionCall": {}}],
        [{"functionCall": {"name": ""}}],
        [{"functionCall": {"name": "calculator"}}],
        [{"functionCall": {"name": 123, "args": {}}}],
        [{"functionCall": {"name": "calculator", "args": "not-a-dict"}}],
        [{"functionCall": {"name": "calculator", "args": {"input": 123}}}],
        [{"functionCall": {"name": "calculator", "args": {"input": None}}}],
        [{"functionCall": {"name": "calculator", "args": {"a": 1, "b": 2}}}],
    ],
)
@patch(URLOPEN_TARGET)
def test_gemini_provider_malformed_function_calls_raise(mock_urlopen, parts):
    mock_urlopen.return_value = make_response(generate_content_response(parts))
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- generate() vs tool calls ----------------------------------------------------


@patch(URLOPEN_TARGET)
def test_gemini_provider_generate_rejects_tool_call_responses(mock_urlopen):
    mock_urlopen.return_value = make_response(generate_content_response([make_function_call()]))
    provider = make_provider()

    with pytest.raises(ProviderResponseError, match="generate_response"):
        provider.generate("hi")


# --- Network and error mapping ---------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503, 504])
@patch(URLOPEN_TARGET)
def test_gemini_provider_http_status_errors_raise_clean_exception(mock_urlopen, status):
    mock_urlopen.side_effect = urllib.error.HTTPError(DEFAULT_ENDPOINT, status, "error", None, None)
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=str(status)):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_network_failure_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_timeout_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = TimeoutError()
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_http_error_includes_response_body_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT,
        429,
        "Too Many Requests",
        None,
        io.BytesIO(b'{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'),
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match="RESOURCE_EXHAUSTED"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_http_error_body_snippet_is_truncated(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT,
        500,
        "Internal Server Error",
        None,
        io.BytesIO(b"x" * 500),
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=r"\.\.\.$"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_http_error_with_empty_body_has_no_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 500, "Internal Server Error", None, io.BytesIO(b"  ")
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=r"status 500$"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_gemini_provider_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider(api_key="super-secret")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret" not in str(exc_info.value)


@patch(URLOPEN_TARGET)
def test_gemini_provider_http_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 401, "Unauthorized", None, None
    )
    provider = make_provider(api_key="super-secret-key")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret-key" not in str(exc_info.value)


def test_gemini_provider_repr_does_not_leak_api_key():
    provider = make_provider(api_key="super-secret")

    assert "super-secret" not in repr(provider.config)
