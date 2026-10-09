"""Request/response wire formats of the HTTP, OpenAI-compatible and Anthropic providers."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.anthropic_provider import AnthropicProvider
from nexusagent.http_provider import HttpProvider
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.provider import (
    Message,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolSpec,
)

URLOPEN = "nexusagent.http_provider.urllib.request.urlopen"
TOOLS = [ToolSpec("calculator", "Performs basic arithmetic operations.")]
CALL = ToolCallRequest("calculator", "2 + 3", call_id="c1")
HISTORY = [
    Message("system", "Be brief."),
    Message("user", "what is 2 + 3?"),
    Message("assistant", tool_call=CALL),
    Message("tool", "5", tool_call=CALL),
]


def reply(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


def sent(mock):
    request = mock.call_args.args[0]
    return json.loads(request.data), {k.lower(): v for k, v in request.header_items()}, request


# ---------------- generic HTTP ----------------


def http(**kw):
    return HttpProvider(ProviderConfig(endpoint="https://x.test/gen", model="m", **kw))


@patch(URLOPEN)
def test_http_respond_sends_messages_and_tools(mock):
    mock.return_value = reply({"output": "hi"})

    http().respond(HISTORY, TOOLS)

    body, _, _ = sent(mock)
    assert body["model"] == "m"
    assert body["input"] == "what is 2 + 3?"
    assert body["tools"] == [{"name": "calculator", "description": TOOLS[0].description}]
    assert body["messages"][-1] == {
        "role": "tool",
        "content": "5",
        "tool_name": "calculator",
        "tool_input": "2 + 3",
        "call_id": "c1",
    }


@patch(URLOPEN)
def test_http_respond_text(mock):
    mock.return_value = reply({"output": "hello"})
    assert http().respond([Message("user", "x")]) == TextResponse("hello")


@patch(URLOPEN)
def test_http_respond_tool_call(mock):
    mock.return_value = reply({"tool_name": "echo", "tool_input": "x", "call_id": "z"})
    assert http().respond([Message("user", "x")]) == ToolCallRequest("echo", "x", "z")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tool_name": "", "tool_input": "x"},
        {"tool_name": "echo"},
        {"tool_name": "echo", "tool_input": "x", "call_id": 5},
        {"output": "  "},
    ],
)
@patch(URLOPEN)
def test_http_respond_rejects_malformed_payloads(mock, payload):
    mock.return_value = reply(payload)
    with pytest.raises(ProviderResponseError):
        http().respond([Message("user", "x")])


@patch(URLOPEN)
def test_http_generate_body_is_unchanged(mock):
    mock.return_value = reply({"output": "hi"})
    http().generate("p")
    assert sent(mock)[0] == {"model": "m", "input": "p"}


@patch(URLOPEN, side_effect=ConnectionResetError("boom secret-key"))
def test_connection_reset_becomes_provider_request_error(_):
    with pytest.raises(ProviderRequestError) as info:
        http(api_key="secret-key").generate("p")
    assert "secret-key" not in str(info.value)


# ---------------- OpenAI-compatible ----------------


def oai(**kw):
    return OpenAIProvider(ProviderConfig(model="gpt-x", api_key="k", **kw))


@patch(URLOPEN)
def test_openai_request_shape(mock):
    mock.return_value = reply({"choices": [{"message": {"content": "5"}}]})

    oai().respond(HISTORY, TOOLS)

    body, headers, request = sent(mock)
    assert request.full_url == "https://api.openai.com/v1/chat/completions"
    assert headers["authorization"] == "Bearer k"
    assert body["model"] == "gpt-x"
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assistant = body["messages"][2]
    assert assistant["tool_calls"][0]["id"] == "c1"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"input": "2 + 3"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "5"}
    function = body["tools"][0]["function"]
    assert function["name"] == "calculator"
    assert function["parameters"]["required"] == ["input"]


@patch(URLOPEN)
def test_openai_custom_endpoint_and_no_key_for_local_servers(mock):
    mock.return_value = reply({"choices": [{"message": {"content": "hi"}}]})
    provider = OpenAIProvider(
        ProviderConfig(model="llama3", endpoint="http://localhost:11434/v1/chat/completions")
    )

    provider.respond([Message("user", "x")])

    _, headers, request = sent(mock)
    assert request.full_url == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in headers


@patch(URLOPEN)
def test_openai_omits_tools_when_none(mock):
    mock.return_value = reply({"choices": [{"message": {"content": "hi"}}]})
    oai().respond([Message("user", "x")])
    assert "tools" not in sent(mock)[0]


@patch(URLOPEN)
def test_openai_parses_tool_call(mock):
    mock.return_value = reply(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_9",
                                "type": "function",
                                "function": {"name": "echo", "arguments": '{"input": "yo"}'},
                            },
                            {"id": "call_10", "function": {"name": "echo", "arguments": "{}"}},
                        ],
                    }
                }
            ]
        }
    )
    assert oai().respond([Message("user", "x")]) == ToolCallRequest("echo", "yo", "call_9")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "  "}}]},
        {
            "choices": [
                {"message": {"tool_calls": [{"function": {"name": "e", "arguments": "not json"}}]}}
            ]
        },
        {
            "choices": [
                {"message": {"tool_calls": [{"function": {"name": "e", "arguments": "[1]"}}]}}
            ]
        },
    ],
)
@patch(URLOPEN)
def test_openai_rejects_malformed_responses(mock, payload):
    mock.return_value = reply(payload)
    with pytest.raises(ProviderResponseError):
        oai().respond([Message("user", "x")])


@patch(URLOPEN)
def test_openai_generate_returns_text(mock):
    mock.return_value = reply({"choices": [{"message": {"content": "hey"}}]})
    assert oai().generate("x") == "hey"


def test_openai_requires_model():
    with pytest.raises(ProviderConfigurationError):
        OpenAIProvider(ProviderConfig()).respond([Message("user", "x")])


# ---------------- Anthropic ----------------


def anth(**kw):
    return AnthropicProvider(ProviderConfig(model="claude-x", api_key="sk-secret", **kw))


@patch(URLOPEN)
def test_anthropic_request_shape(mock):
    mock.return_value = reply({"content": [{"type": "text", "text": "5"}]})

    anth().respond(HISTORY, TOOLS)

    body, headers, request = sent(mock)
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-secret"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in headers
    assert body["system"] == "Be brief."
    assert body["max_tokens"] > 0
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["messages"][1]["content"] == [
        {"type": "tool_use", "id": "c1", "name": "calculator", "input": {"input": "2 + 3"}}
    ]
    assert body["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "c1", "content": "5"}
    ]
    assert body["tools"][0]["input_schema"]["required"] == ["input"]


@patch(URLOPEN)
def test_anthropic_parses_text_blocks(mock):
    mock.return_value = reply(
        {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    )
    assert anth().respond([Message("user", "x")]) == TextResponse("ab")


@patch(URLOPEN)
def test_anthropic_parses_tool_use(mock):
    mock.return_value = reply(
        {
            "content": [
                {"type": "text", "text": "Let me compute."},
                {"type": "tool_use", "id": "tu_1", "name": "calculator", "input": {"input": "1+1"}},
            ]
        }
    )
    assert anth().respond([Message("user", "x")]) == ToolCallRequest("calculator", "1+1", "tu_1")


@pytest.mark.parametrize(
    "payload",
    [{}, {"content": []}, {"content": [{"type": "text", "text": " "}]}, {"content": "str"}],
)
@patch(URLOPEN)
def test_anthropic_rejects_malformed_responses(mock, payload):
    mock.return_value = reply(payload)
    with pytest.raises(ProviderResponseError):
        anth().respond([Message("user", "x")])


@pytest.mark.parametrize(
    "config", [ProviderConfig(api_key="k"), ProviderConfig(model="m")], ids=["no-model", "no-key"]
)
def test_anthropic_requires_model_and_key(config):
    with pytest.raises(ProviderConfigurationError):
        AnthropicProvider(config).respond([Message("user", "x")])


@patch(URLOPEN, side_effect=Exception("unexpected"))
def test_provider_errors_never_include_api_key(_):
    with pytest.raises(Exception) as info:
        anth().generate("x")
    assert "sk-secret" not in str(info.value)
