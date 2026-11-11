import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.openai_provider import DEFAULT_ENDPOINT, OpenAIProvider
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


def chat_response(
    content: str | None = None,
    tool_calls: list[object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Build a minimal OpenAI chat.completion payload."""
    message: dict[str, object] = {}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls

    choice: dict[str, object] = {"message": message}
    payload: dict[str, object] = {"choices": [choice]}
    payload.update(overrides)
    return payload


def make_tool_call(
    name: str = "calculator",
    arguments: str = '{"input": "2 + 3"}',
    call_id: str = "call_abcd",
) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def make_provider(**config_kwargs: object) -> OpenAIProvider:
    kwargs: dict[str, object] = {"model": "test-model"}
    kwargs.update(config_kwargs)
    return OpenAIProvider(ProviderConfig(**kwargs))  # type: ignore[arg-type]


# --- Construction and identity -------------------------------------------------


def test_openai_provider_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("constructing OpenAIProvider must not connect")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    OpenAIProvider(ProviderConfig(model="test-model"))


def test_openai_provider_is_a_provider():
    assert isinstance(make_provider(), Provider)


def test_openai_provider_defaults_to_no_config():
    provider = OpenAIProvider()

    assert provider.config == ProviderConfig()


# --- Configuration validation --------------------------------------------------


def test_openai_provider_missing_model_raises():
    provider = OpenAIProvider(ProviderConfig())

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


def test_openai_provider_whitespace_only_model_raises():
    provider = make_provider(model="   ")

    with pytest.raises(ProviderConfigurationError, match="model"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_openai_provider_invalid_timeout_raises(timeout):
    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError, match="timeout"):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_openai_provider_invalid_timeout_does_not_perform_network_access(monkeypatch, timeout):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid timeout must not trigger a network request")

    monkeypatch.setattr(URLOPEN_TARGET, fail_if_called)

    provider = make_provider(timeout=timeout)

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


# --- Request shape -------------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_openai_provider_sends_expected_request(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    config = ProviderConfig(
        model="test-model",
        api_key="secret-key",
        endpoint="https://example.test/v1/chat/completions",
        timeout=5,
    )
    provider = OpenAIProvider(config)

    provider.generate("hi there")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://example.test/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer secret-key"

    body = json.loads(request.data)
    assert body == {"model": "test-model", "messages": [{"role": "user", "content": "hi there"}]}

    assert mock_urlopen.call_args.kwargs["timeout"] == 5


@patch(URLOPEN_TARGET)
def test_openai_provider_uses_default_endpoint_without_configuration(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider()

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == DEFAULT_ENDPOINT
    assert mock_urlopen.call_args.kwargs["timeout"] == 30.0


@patch(URLOPEN_TARGET)
def test_openai_provider_supports_local_servers_via_endpoint_override(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider(endpoint="http://localhost:11434/v1/chat/completions")

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:11434/v1/chat/completions"


@patch(URLOPEN_TARGET)
def test_openai_provider_without_api_key_omits_authorization_header(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider(api_key=None)

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.get_header("Authorization") is None


@patch(URLOPEN_TARGET)
def test_openai_provider_advertises_tools_as_single_input_functions(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider()

    provider.generate_response(
        "hi",
        tools=(ToolSpec("calculator", "Performs basic arithmetic operations."),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Performs basic arithmetic operations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "Raw text input for the tool.",
                        }
                    },
                    "required": ["input"],
                },
            },
        }
    ]


@patch(URLOPEN_TARGET)
def test_openai_provider_omits_tools_key_without_tools(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider()

    provider.generate_response("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert "tools" not in body


# --- Stateless tool-result rehydration -----------------------------------------


@patch(URLOPEN_TARGET)
def test_openai_provider_rehydrates_one_tool_result(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
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
            "content": None,
            "tool_calls": [
                {
                    "id": "call_0",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": json.dumps({"input": "2 + 3"}),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_0", "content": "5"},
    ]


@patch(URLOPEN_TARGET)
def test_openai_provider_rehydrates_several_tool_results_in_order(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
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
    assert roles == ["user", "assistant", "tool", "assistant", "tool"]
    assert body["messages"][1]["tool_calls"][0]["id"] == "call_0"
    assert body["messages"][2]["tool_call_id"] == "call_0"
    assert body["messages"][3]["tool_calls"][0]["id"] == "call_1"
    assert body["messages"][4]["tool_call_id"] == "call_1"
    assert body["messages"][4]["content"] == "5"


@patch(URLOPEN_TARGET)
def test_openai_provider_marks_error_tool_results_with_prefix(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider()

    provider.generate_response(
        "hi",
        tool_results=(ToolResult("calculator", "nonsense", "invalid expression", is_error=True),),
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["messages"][-1]["content"] == "Error: invalid expression"


@patch(URLOPEN_TARGET)
def test_openai_provider_successful_tool_results_have_no_error_prefix(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello"))
    provider = make_provider()

    provider.generate_response("hi", tool_results=(ToolResult("echo", "hi", "hi echoed"),))

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["messages"][-1]["content"] == "hi echoed"


# --- Text response parsing ------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_openai_provider_returns_text_content(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="hello world"))
    provider = make_provider()

    assert provider.generate("hi") == "hello world"


@patch(URLOPEN_TARGET)
def test_openai_provider_preserves_surrounding_whitespace_in_content(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content=" hello "))
    provider = make_provider()

    assert provider.generate("hi") == " hello "


@patch(URLOPEN_TARGET)
def test_openai_provider_generate_response_returns_text_response(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="answer"))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == TextResponse("answer")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"no_choices": True},
        {"choices": []},
        {"choices": "not-a-list"},
        {"choices": [{"no_message": True}]},
        {"choices": [{"message": "not-a-dict"}]},
        {"choices": ["not-a-dict"]},
    ],
)
@patch(URLOPEN_TARGET)
def test_openai_provider_malformed_payload_raises(mock_urlopen, payload):
    mock_urlopen.return_value = make_response(payload)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("content", [None, 123, ["hello"], "", "   ", "\n"])
@patch(URLOPEN_TARGET)
def test_openai_provider_invalid_content_raises(mock_urlopen, content):
    mock_urlopen.return_value = make_response(chat_response(content=content))
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"text"', b"42"])
@patch(URLOPEN_TARGET)
def test_openai_provider_invalid_json_raises(mock_urlopen, raw):
    mock_urlopen.return_value = make_raw_response(raw)
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- Tool call parsing -----------------------------------------------------------


@patch(URLOPEN_TARGET)
def test_openai_provider_parses_tool_call_with_input_key(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(tool_calls=[make_tool_call()]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_openai_provider_accepts_models_that_pick_their_own_parameter_name(mock_urlopen):
    call = make_tool_call(name="calculator", arguments='{"expression": "2 + 3"}')
    mock_urlopen.return_value = make_response(chat_response(tool_calls=[call]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == ToolCallRequest(tool_name="calculator", tool_input="2 + 3")


@patch(URLOPEN_TARGET)
def test_openai_provider_uses_first_of_several_tool_calls(mock_urlopen):
    calls = [make_tool_call(name="echo"), make_tool_call(name="uppercase")]
    mock_urlopen.return_value = make_response(chat_response(tool_calls=calls))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)
    assert response.tool_name == "echo"


@patch(URLOPEN_TARGET)
def test_openai_provider_prefers_tool_call_over_content(mock_urlopen):
    mock_urlopen.return_value = make_response(
        chat_response(content="some text", tool_calls=[make_tool_call()])
    )
    provider = make_provider()

    response = provider.generate_response("hi")

    assert isinstance(response, ToolCallRequest)


@patch(URLOPEN_TARGET)
def test_openai_provider_empty_tool_calls_falls_back_to_text(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(content="all done", tool_calls=[]))
    provider = make_provider()

    response = provider.generate_response("hi")

    assert response == TextResponse("all done")


@pytest.mark.parametrize(
    "tool_calls",
    [
        "not-a-list",
        123,
        [42],
        [{"no_function": True}],
        [{"function": "not-a-dict"}],
        [{"function": {"name": "", "arguments": "{}"}}],
        [{"function": {"name": "calculator"}}],
        [{"function": {"name": 123, "arguments": "{}"}}],
    ],
)
@patch(URLOPEN_TARGET)
def test_openai_provider_malformed_tool_calls_raise(mock_urlopen, tool_calls):
    mock_urlopen.return_value = make_response(chat_response(tool_calls=tool_calls))
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize(
    "arguments",
    ["{not json}", "123", "null", '{"input": 123}', '{"input": null}', '{"a": 1, "b": 2}'],
)
@patch(URLOPEN_TARGET)
def test_openai_provider_unusable_arguments_raise(mock_urlopen, arguments):
    call = make_tool_call(arguments=arguments)
    mock_urlopen.return_value = make_response(chat_response(tool_calls=[call]))
    provider = make_provider()

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


# --- generate() vs tool calls ----------------------------------------------------


@patch(URLOPEN_TARGET)
def test_openai_provider_generate_rejects_tool_call_responses(mock_urlopen):
    mock_urlopen.return_value = make_response(chat_response(tool_calls=[make_tool_call()]))
    provider = make_provider()

    with pytest.raises(ProviderResponseError, match="generate_response"):
        provider.generate("hi")


# --- Network and error mapping ---------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503, 504])
@patch(URLOPEN_TARGET)
def test_openai_provider_http_status_errors_raise_clean_exception(mock_urlopen, status):
    mock_urlopen.side_effect = urllib.error.HTTPError(DEFAULT_ENDPOINT, status, "error", None, None)
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=str(status)):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_openai_provider_network_failure_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_openai_provider_timeout_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = TimeoutError()
    provider = make_provider()

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_openai_provider_http_error_includes_response_body_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT,
        429,
        "Too Many Requests",
        None,
        io.BytesIO(b'{"error": "rate limit exceeded"}'),
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match="rate limit exceeded"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_openai_provider_http_error_body_snippet_is_truncated(mock_urlopen):
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
def test_openai_provider_http_error_with_empty_body_has_no_snippet(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 500, "Internal Server Error", None, io.BytesIO(b"  ")
    )
    provider = make_provider()

    with pytest.raises(ProviderRequestError, match=r"status 500$"):
        provider.generate("hi")


@patch(URLOPEN_TARGET)
def test_openai_provider_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = make_provider(api_key="super-secret")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret" not in str(exc_info.value)


@patch(URLOPEN_TARGET)
def test_openai_provider_http_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        DEFAULT_ENDPOINT, 401, "Unauthorized", None, None
    )
    provider = make_provider(api_key="super-secret-key")

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret-key" not in str(exc_info.value)


def test_openai_provider_repr_does_not_leak_api_key():
    provider = make_provider(api_key="super-secret")

    assert "super-secret" not in repr(provider.config)
