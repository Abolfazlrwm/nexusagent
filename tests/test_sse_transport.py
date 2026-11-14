"""Contract tests for the shared SSE streaming transport ``post_sse()``."""

import http.client
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.http_provider import post_sse
from nexusagent.provider import ProviderRequestError

URLOPEN_TARGET = "nexusagent.http_provider.urllib.request.urlopen"


def make_stream(lines: list[bytes]) -> MagicMock:
    """Build an open HTTP response whose body is ``lines`` (bytes per line)."""
    response = MagicMock()
    response.__iter__.return_value = iter(lines)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def sse(*events: str) -> list[bytes]:
    """Encode SSE events (multi-line strings) into one response line each."""
    lines: list[bytes] = []
    for block in events:
        for line in block.split("\n"):
            lines.append(line.encode("utf-8") + b"\n")
    return lines


def event(data: str) -> str:
    return f"data: {data}\n"


def test_post_sse_yields_single_event_payload():
    with patch(URLOPEN_TARGET, return_value=make_stream(sse(event('{"a": 1}')))):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"a": 1}']


def test_post_sse_yields_multiple_events_in_order():
    lines = sse(event('{"n": 1}'), event('{"n": 2}'), event('{"n": 3}'))
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == [
            '{"n": 1}',
            '{"n": 2}',
            '{"n": 3}',
        ]


def test_post_sse_joins_multi_line_data_field_with_newline():
    lines = sse("data: line one\ndata: line two\n")
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ["line one\nline two"]


def test_post_sse_ignores_comment_lines():
    lines = sse(": keep-alive comment", event('{"a": 1}'))
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"a": 1}']


def test_post_sse_ignores_event_id_and_retry_fields():
    lines = sse('event: content_block_delta\nid: 42\nretry: 1000\ndata: {"type": "x"}\n')
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"type": "x"}']


def test_post_sse_handles_crlf_line_endings():
    lines = [
        b'data: {"a": 1}\r\n',
        b"\r\n",
        b'data: {"a": 2}\r\n',
        b"\r\n",
    ]
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == [
            '{"a": 1}',
            '{"a": 2}',
        ]


def test_post_sse_flushes_final_event_without_trailing_blank_line():
    raw = b'data: {"last": true}\n'
    with patch(URLOPEN_TARGET, return_value=make_stream([raw])):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"last": true}']


def test_post_sse_empty_stream_yields_nothing():
    with patch(URLOPEN_TARGET, return_value=make_stream([])):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == []


def test_post_sse_data_field_without_space_after_colon():
    lines = sse('data:{"a": 1}\n')
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"a": 1}']


def test_post_sse_decodes_multibyte_utf8_payloads():
    payload = {"text": "سلام"}
    lines = sse(event(json.dumps(payload, ensure_ascii=False)))
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == [
            json.dumps(payload, ensure_ascii=False)
        ]


def test_post_sse_encodes_body_as_json_and_uses_post():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen):
        list(post_sse("https://x.test/sse", {"model": "m", "n": 1}, {}, 1.0))

    assert captured["method"] == "POST"
    assert captured["body"] == {"model": "m", "n": 1}


def test_post_sse_sends_accept_event_stream_header():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen):
        list(post_sse("https://x.test/sse", {}, {"Content-Type": "application/json"}, 1.0))

    assert captured["headers"]["Accept"] == "text/event-stream"
    assert captured["headers"]["Content-type"] == "application/json"


def test_post_sse_passes_caller_auth_header():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = request.headers
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen):
        list(post_sse("https://x.test/sse", {}, {"Authorization": "Bearer key"}, 1.0))

    assert captured["headers"]["Authorization"] == "Bearer key"


def test_post_sse_passes_timeout_to_urlopen():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return make_stream([])

    with patch(URLOPEN_TARGET, side_effect=fake_urlopen):
        list(post_sse("https://x.test/sse", {}, {}, 4.5))

    assert captured["timeout"] == 4.5


def test_post_sse_http_error_maps_to_provider_request_error_with_snippet():
    error = urllib.error.HTTPError(
        "https://x.test/sse",
        401,
        "Unauthorized",
        None,
        io.BytesIO(b'{"error": "invalid api key"}'),
    )
    with (
        patch(URLOPEN_TARGET, side_effect=error),
        pytest.raises(ProviderRequestError, match="401"),
    ):
        post_sse("https://x.test/sse", {}, {}, 1.0)


def test_post_sse_http_error_snippet_includes_backend_body():
    error = urllib.error.HTTPError(
        "https://x.test/sse", 429, "Too Many Requests", None, io.BytesIO(b"rate limited")
    )
    with (
        patch(URLOPEN_TARGET, side_effect=error),
        pytest.raises(ProviderRequestError, match="rate limited"),
    ):
        post_sse("https://x.test/sse", {}, {}, 1.0)


def test_post_sse_url_error_maps_to_provider_request_error():
    with (
        patch(URLOPEN_TARGET, side_effect=urllib.error.URLError("connection refused")),
        pytest.raises(ProviderRequestError, match="connection refused"),
    ):
        post_sse("https://x.test/sse", {}, {}, 1.0)


def test_post_sse_timeout_error_maps_to_provider_request_error():
    with (
        patch(URLOPEN_TARGET, side_effect=TimeoutError()),
        pytest.raises(ProviderRequestError, match="timed out"),
    ):
        post_sse("https://x.test/sse", {}, {}, 1.0)


def test_post_sse_mid_stream_http_exception_surfaces_during_iteration():
    def broken_iter():
        yield b'data: {"a": 1}\n'
        yield b"\n"
        raise http.client.IncompleteRead(b"partial")

    response = make_stream([])
    response.__iter__.return_value = broken_iter()
    with patch(URLOPEN_TARGET, return_value=response):
        iterator = post_sse("https://x.test/sse", {}, {}, 1.0)

    assert next(iterator) == '{"a": 1}'

    with pytest.raises(ProviderRequestError, match="HTTP stream failed"):
        next(iterator)


def test_post_sse_mid_stream_os_error_surfaces_during_iteration():
    def broken_iter():
        yield b"data: x\n"
        yield b"\n"
        raise OSError("connection reset")

    response = make_stream([])
    response.__iter__.return_value = broken_iter()
    with patch(URLOPEN_TARGET, return_value=response):
        iterator = post_sse("https://x.test/sse", {}, {}, 1.0)

    assert next(iterator) == "x"

    with pytest.raises(ProviderRequestError, match="connection reset"):
        next(iterator)


def test_post_sse_ignores_lines_that_are_not_data_fields():
    lines = sse("retry: 500\n", ": ping", event('{"a": 1}'))
    with patch(URLOPEN_TARGET, return_value=make_stream(lines)):
        assert list(post_sse("https://x.test/sse", {}, {}, 1.0)) == ['{"a": 1}']


def test_post_sse_http_error_without_readable_body_still_maps_to_request_error():
    class UnreadableBody(io.BytesIO):
        def read(self, *args, **kwargs):
            raise OSError("pipe closed")

    error = urllib.error.HTTPError(
        "https://x.test/sse", 500, "Server Error", None, UnreadableBody()
    )
    with (
        patch(URLOPEN_TARGET, side_effect=error),
        pytest.raises(ProviderRequestError, match="500"),
    ):
        post_sse("https://x.test/sse", {}, {}, 1.0)
