import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.anthropic_provider import (
    DEFAULT_ENDPOINT,
    DEFAULT_MAX_TOKENS,
    AnthropicProvider,
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


def message_response(
    text_blocks: list[object] | None = None,
    tool_use_blocks: list[object] | None = None,
    extra_blocks: list[object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Build a minimal Anthropic Messages API response payload."""
    content: list[object] = []
    content.extend(extra_blocks or [])
    if text_blocks:
        content.extend(text_blocks)
    if tool_use_blocks:
        content.extend(tool_use_blocks)

    payload: dict[str, object] = {"content": content, "stop_reason": "end_turn"}
    payload.update(overrides)
    return payload


def text_block(text: object) -> dict[str, object]:
    return {"type": "text", "text": text}


def make_tool_use(
    name: str = "calculator",
    input_obj: object = {"input": "2 + 3"},
    block_id: str = "toolu_01AbCdEf",
) -> dict[str, object]:
    return {"type": "tool_use", "id": block_id, "name": name, "input": input_obj}


def make_provider(**config_kwargs: object) -> AnthropicProvider:
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return AnthropicProvider(ProviderConfig(**kwargs))  # type: ignore[arg-type]


# --- Construction and identity -------------------------------------------------


def test_anthropic_provider_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("constructing AnthropicProvider must not connect")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    AnthropicProvider(ProviderConfig(model="test-model"))


def test_anthropic_provider_is_a_provider():
    assert isinstance(make_provider(), Provider)


def test_anthropic_provider_defaults_to_no_config():
    provider = AnthropicProvider()

    assert provider.config == ProviderConfig()
    assert provider.max_tokens == DEFAULT_MAX_TOKENS


def test_anthropic_provider_accepts_explicit_max_tokens():
    provider = AnthropicProvider(max_tokens=512)

    assert provider.max_tokens == 512


# --- Configuration validation --------------------------------------------------


def test_anthropic_provider_missing_model_raises():
    provider = AnthropicProvider(ProviderConfig())

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


def test_anthropic_provider_whitespace_only_model_raises():
    provider = make_provider(model="   ")

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_anthropic_provider_invalid_timeout_raises(timeout):
    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError, match="timeout"):
        provider.generate("hi")


@pytest.mark.parametrize("max_tokens", [0, -1, 1.5, "1024", True])
def test_anthropic_provider_invalid_max_tokens_raises(max_tokens):
    provider = AnthropicProvider(ProviderConfig(model="test-model"), max_tokens=max_tokens)

    with pytest.raises(ProviderConfigurationError, match="max_tokens"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_anthropic_provider_invalid_timeout_does_not_perform_network_access(monkeypatch, timeout):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid timeout must not trigger a network request")

    monkeypatch.setattr(URLOPEN_TARGET, fail_if_called)

    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


def test_anthropic_provider_invalid_max_tokens_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid max_tokens must not trigger a network request")

    monkeypatch.setattr(URLOPEN_TARGET, fail_if_called)

    provider = AnthropicProvider(ProviderConfig(model="test-model"), max_tokens=0)

    with pytest.raises(ProviderConfigurationError, match="max_tokens"):
        provider.generate("hi")


# --- Request shape -------------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_anthropic_provider_sends_expected_request(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    config = ProviderConfig(
        model="test-model",
        api_key="secret-key",
        endpoint="https://example.test/v1/messages",
        timeout=5,
    )
    provider = AnthropicProvider(config)

    provider.generate("hi there")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://example.test/v1/messages"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-api-key") == "secret-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"

    body = json.loads(request.data)
    assert body["model"] == "test-model"
    assert body["max_tokens"] == DEFAULT_MAX_TOKENS
    assert body["messages"] == [{"role": "user", "content": "hi there"}]

    assert mock_urlopen.call_args.kwargs["timeout"] == 5


@patch(URLOPEN_TARGET)
def test_anthropic_provider_uses_default_endpoint_without_configuration(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == DEFAULT_ENDPOINT
    assert mock_urlopen.call_args.kwargs["timeout"] == 30.0


@patch(URLOPEN_TARGET)
def test_anthropic_provider_supports_gateways_via_endpoint_override(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider(endpoint="http://localhost:8080/v1/messages")

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:8080/v1/messages"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_without_api_key_omits_auth_header(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider(api_key=None)

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.get_header("X-api-key") is None


@patch(URLOPEN_TARGET)
def test_anthropic_provider_sends_configured_max_tokens(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = AnthropicProvider(ProviderConfig(model="test-model"), max_tokens=256)

    provider.generate("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["max_tokens"] == 256


@patch(URLOPEN_TARGET)
def test_anthropic_provider_advertises_tools_with_input_schema(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
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
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Raw text input for the tool.",
                    }
                },
                "required": ["input"],
            },
        }
    ]


@patch(URLOPEN_TARGET)
def test_anthropic_provider_omits_tools_key_without_tools(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate_response("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert "tools" not in body


# --- Stateless tool-result rehydration -----------------------------------------


@patch(URLOPEN_TARGET)
def test_anthropic_provider_rehydrates_one_tool_result(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate_response(
        "What is 2 + 3?",
        tool_results=(ToolResult("calculator", "2 + 3", "5"),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["messages"] == [
        {"role": "user", "content": "What is 2 + 3?"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_0",
                    "name": "calculator",
                    "input": {"input": "2 + 3"},
                }
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_0", "content": "5"}],
        },
    ]


@patch(URLOPEN_TARGET)
def test_anthropic_provider_rehydrates_several_tool_results_in_order(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate_response(
        "do two things",
        tool_results=(
            ToolResult("echo", "first", "first echoed"),
            ToolResult("calculator", "2 + 3", "5"),
        ),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant", "user", "assistant", "user"]
    assert body["messages"][1]["content"][0]["id"] == "call_0"
    assert body["messages"][2]["content"][0]["tool_use_id"] == "call_0"
    assert body["messages"][3]["content"][0]["id"] == "call_1"
    assert body["messages"][4]["content"][0]["tool_use_id"] == "call_1"
    assert body["messages"][4]["content"][0]["content"] == "5"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_marks_error_tool_results_with_native_flag(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate_response(
        "hi",
        tool_results=(ToolResult("calculator", "nonsense", "invalid expression", is_error=True),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    tool_result = body["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert tool_result["content"] == "invalid expression"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_successful_tool_results_carry_no_error_flag(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello")]))
    provider = make_provider()

    provider.generate_response("hi", tool_results=(ToolResult("echo", "hi", "hi echoed"),))

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert "is_error" not in body["messages"][-1]["content"][0]


# --- Text response parsing ------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_anthropic_provider_returns_text_content(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("hello world")]))
    provider = make_provider()

    assert provider.generate("hi") == "hello world"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_preserves_surrounding_whitespace_in_text(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block(" hello ")]))
    provider = make_provider()

    assert provider.generate("hi") == " hello "


@patch(URLOPEN_TARGET)
def test_anthropic_provider_joins_multiple_text_blocks(mock_urlopen):
    mock_urlopen.return_value = make_response(
        message_response([text_block("hello "), text_block("world")])
    )
    provider = make_provider()

    assert provider.generate("hi") == "hello world"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_generate_response_returns_text_response(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response([text_block("answer")]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == TextResponse("answer")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_skips_unknown_content_block_types(mock_urlopen):
    mock_urlopen.return_value = make_response(
        message_response(
            [text_block("answer")],
            extra_blocks=[{"type": "server_tool_use", "id": "srv_01"}],
        )
    )
    provider = make_provider()

    assert provider.generate("hi") == "answer"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"no_content": True},
        {"content": []},
        {"content": "not-a-list"},
        {"content": ["not-a-dict"]},
        {"content": [42]},
        {"content": [{"type": "text", "text": None}]},
        {"content": [{"type": "text", "text": 123}]},
        {"content": [{"type": "text"}]},
        {"content": [{"type": "unknown_kind"}]},
    ],
)
@patch(URLOPEN_TARGET)
def test_anthropic_provider_malformed_payloads_raise(mock_urlopen, payload):
    mock_urlopen.return_value = make_response(payload)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"text"', b"42"])
@patch(URLOPEN_TARGET)
def test_anthropic_provider_invalid_json_raises(mock_urlopen, raw):
    mock_urlopen.return_value = make_raw_response(raw)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- Tool call parsing -----------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_anthropic_provider_parses_tool_use_with_input_key(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response(tool_use_blocks=[make_tool_use()]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_accepts_models_that_pick_their_own_parameter_name(mock_urlopen):
    block = make_tool_use(name="calculator", input_obj={"expression": "2 + 3"})
    mock_urlopen.return_value = make_response(message_response(tool_use_blocks=[block]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_uses_first_of_several_tool_use_blocks(mock_urlopen):
    blocks = [make_tool_use(name="echo"), make_tool_use(name="uppercase")]
    mock_urlopen.return_value = make_response(message_response(tool_use_blocks=blocks))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)
    assert response.tool_name == "echo"


@patch(URLOPEN_TARGET)
def test_anthropic_provider_prefers_tool_use_over_text(mock_urlopen):
    mock_urlopen.return_value = make_response(
        message_response(text_blocks=[text_block("some text")], tool_use_blocks=[make_tool_use()])
    )
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)


@pytest.mark.parametrize(
    "tool_use_blocks",
    [
        [42],
        [{"type": "tool_use"}],
        [{"type": "tool_use", "name": ""}],
        [{"type": "tool_use", "name": "calculator"}],
        [{"type": "tool_use", "name": 123, "input": {}}],
        [{"type": "tool_use", "name": "calculator", "input": "not-a-dict"}],
        [{"type": "tool_use", "name": "calculator", "input": {"input": 123}}],
        [{"type": "tool_use", "name": "calculator", "input": {"input": None}}],
        [{"type": "tool_use", "name": "calculator", "input": {"a": 1, "b": 2}}],
    ],
)
@patch(URLOPEN_TARGET)
def test_anthropic_provider_malformed_tool_use_blocks_raise(mock_urlopen, tool_use_blocks):
    mock_urlopen.return_value = make_response(message_response(tool_use_blocks=tool_use_blocks))
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- generate() vs tool calls ----------------------------------------------------


@patch(URLOPEN_TARGET)
def test_anthropic_provider_generate_rejects_tool_call_responses(mock_urlopen):
    mock_urlopen.return_value = make_response(message_response(tool_use_blocks=[make_tool_use()]))
    provider = make_provider()

    with pytest.raises(ProviderResponseError, match="generate_response"):
        provider.generate("hi")


# --- Network and error mapping ---------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503, 504])
@patch(URLOPEN_TARGET)
def test_anthropic_provider_http_status_errors_raise_clean_exception(mock_urlopen, status):
    mock_urlopen.side_effect = urllib.error.HTTPError(DEFAULT_ENDPOINT, status, "error", None, None)
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=str(status)):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_network_failure_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_timeout_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = TimeoutError()
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_http_error_includes_response_body_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT,
        429,
        "Too Many Requests",
        None,
        io.BytesIO(b'{"type": "error", "error": {"type": "rate_limit_error"}}'),
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match="rate_limit_error"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_http_error_body_snippet_is_truncated(mock_urlopen):
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
def test_anthropic_provider_http_error_with_empty_body_has_no_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 500, "Internal Server Error", None, io.BytesIO(b"  ")
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=r"status 500$"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_anthropic_provider_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider(api_key="super-secret")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret" not in str(exc_info.value)


@patch(URLOPEN_TARGET)
def test_anthropic_provider_http_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 401, "Unauthorized", None, None
    )
    provider = make_provider(api_key="super-secret-key")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret-key" not in str(exc_info.value)


def test_anthropic_provider_repr_does_not_leak_api_key():
    provider = make_provider(api_key="super-secret")

    assert "super-secret" not in repr(provider.config)
