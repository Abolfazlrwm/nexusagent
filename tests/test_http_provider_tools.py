"""Tests for HttpProvider's tool-call wire format."""

import json
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.http_provider import HttpProvider
from nexusagent.provider import (
    ProviderConfig,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

ENDPOINT = "https://example.test/generate"


def make_response(payload) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def make_provider() -> HttpProvider:
    return HttpProvider(ProviderConfig(model="m", endpoint=ENDPOINT))


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_output_payload_becomes_text_response(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "hello"})

    assert make_provider().generate_response("hi") == TextResponse("hello")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_tool_payload_becomes_tool_call_request(mock_urlopen):
    mock_urlopen.return_value = make_response({"tool_name": "calculator", "tool_input": "2 + 3"})

    assert make_provider().generate_response("hi") == ToolCallRequest("calculator", "2 + 3")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_generate_rejects_tool_call_payload_with_clear_error(mock_urlopen):
    mock_urlopen.return_value = make_response({"tool_name": "echo", "tool_input": "x"})

    with pytest.raises(ProviderResponseError, match="generate_response"):
        make_provider().generate("hi")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"output": "a", "tool_name": "echo", "tool_input": "x"}, "not both"),
        ({"tool_name": "", "tool_input": "x"}, "tool_name"),
        ({"tool_name": 3, "tool_input": "x"}, "tool_name"),
        ({"tool_name": "echo"}, "missing the 'tool_input'"),
        ({"tool_name": "echo", "tool_input": 5}, "tool_input"),
        ({"nothing": "useful"}, "missing the 'output'"),
        ([1, 2], "JSON object"),
    ],
)
@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_invalid_payloads_are_rejected(mock_urlopen, payload, message):
    mock_urlopen.return_value = make_response(payload)

    with pytest.raises(ProviderResponseError, match=message):
        make_provider().generate_response("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_request_body_is_unchanged_without_tools(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "ok"})

    make_provider().generate_response("hi")

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body == {"model": "m", "input": "hi"}


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_request_body_includes_tools_and_tool_results(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "ok"})

    make_provider().generate_response(
        "hi",
        tools=[ToolSpec("echo", "Returns its input unchanged.")],
        tool_results=[ToolResult("echo", "x", "x"), ToolResult("calculator", "1/0", "boom", True)],
    )

    body = json.loads(mock_urlopen.call_args.args[0].data)
    assert body["tools"] == [{"name": "echo", "description": "Returns its input unchanged."}]
    assert body["tool_results"] == [
        {"tool_name": "echo", "tool_input": "x", "output": "x", "is_error": False},
        {"tool_name": "calculator", "tool_input": "1/0", "output": "boom", "is_error": True},
    ]
