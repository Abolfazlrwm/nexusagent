"""Retry/backoff contract tests for the shared HTTP transport (ADR 0011).

The retry window covers the request itself — up to and including the
response headers. Connection errors, timeouts and HTTP 429/5xx are
retried with exponential backoff plus full jitter; other statuses are
permanent and fail fast. A mid-stream failure is never retried.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
from email.message import Message
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.anthropic_provider import AnthropicProvider
from nexusagent.config import Settings
from nexusagent.gemini_provider import GeminiProvider
from nexusagent.http_provider import HttpProvider, post_json, post_sse
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.provider import (
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    TextResponse,
)


def make_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def make_status_error(status: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.test", status, "error", headers, None)


ENDPOINT = "https://example.test/v1/chat/completions"
HEADERS = {"Content-Type": "application/json"}


@patch("nexusagent.http_provider.random.uniform", return_value=0.0)
@patch("nexusagent.http_provider.time.sleep")
@patch("nexusagent.http_provider.urllib.request.urlopen")
class TestPostJsonRetries:
    def test_retries_429_then_succeeds(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = [
            make_status_error(429),
            make_response({"output": "hello"}),
        ]

        result = post_json(ENDPOINT, {"model": "m"}, HEADERS, 30.0, retries=2)

        assert result == {"output": "hello"}
        assert mock_urlopen.call_count == 2
        assert mock_sleep.call_count == 1

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_retries_transient_statuses_then_succeeds(
        self, mock_urlopen, mock_sleep, _mock_uniform, status
    ):
        mock_urlopen.side_effect = [
            make_status_error(status),
            make_response({"output": "ok"}),
        ]

        result = post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert result == {"output": "ok"}
        assert mock_urlopen.call_count == 2

    def test_does_not_retry_permanent_statuses(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = make_status_error(401)

        with pytest.raises(ProviderRequestError, match="status 401"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=3)

        assert mock_urlopen.call_count == 1
        assert mock_sleep.call_count == 0

    def test_exhausted_retries_raise_the_final_error(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = make_status_error(429)

        with pytest.raises(ProviderRequestError, match="status 429"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=2)

        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2

    def test_retries_zero_makes_a_single_attempt(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = make_status_error(503)

        with pytest.raises(ProviderRequestError, match="status 503"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=0)

        assert mock_urlopen.call_count == 1
        assert mock_sleep.call_count == 0

    def test_negative_retries_fail_fast(self, mock_urlopen, mock_sleep, _mock_uniform):
        with pytest.raises(ProviderConfigurationError, match="negative"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=-1)

        assert mock_urlopen.call_count == 0
        assert mock_sleep.call_count == 0

    def test_retries_connection_errors(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = [
            urllib.error.URLError("connection refused"),
            make_response({"output": "ok"}),
        ]

        result = post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert result == {"output": "ok"}
        assert mock_urlopen.call_count == 2

    def test_exhausted_connection_errors_keep_the_message(
        self, mock_urlopen, mock_sleep, _mock_uniform
    ):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        with pytest.raises(ProviderRequestError, match="connection refused"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert mock_urlopen.call_count == 2

    def test_retries_connect_timeouts(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = [
            TimeoutError("connect timed out"),
            make_response({"output": "ok"}),
        ]

        result = post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert result == {"output": "ok"}
        assert mock_urlopen.call_count == 2

    def test_read_stage_timeout_is_not_retried(self, mock_urlopen, mock_sleep, _mock_uniform):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = TimeoutError("read timed out")
        mock_urlopen.return_value = response

        with pytest.raises(ProviderRequestError, match="timed out"):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=3)

        assert mock_urlopen.call_count == 1
        assert mock_sleep.call_count == 0

    def test_retry_after_hint_is_honored(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = [
            make_status_error(429, retry_after="3"),
            make_response({"output": "ok"}),
        ]

        post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert mock_sleep.call_args.args == (3.0,)

    def test_retry_after_hint_is_capped(self, mock_urlopen, mock_sleep, _mock_uniform):
        mock_urlopen.side_effect = [
            make_status_error(429, retry_after="100"),
            make_response({"output": "ok"}),
        ]

        post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        assert mock_sleep.call_args.args == (8.0,)

    def test_unusable_retry_after_falls_back_to_jitter(
        self, mock_urlopen, mock_sleep, mock_uniform
    ):
        mock_urlopen.side_effect = [
            make_status_error(429, retry_after="not-a-number"),
            make_response({"output": "ok"}),
        ]

        post_json(ENDPOINT, {}, HEADERS, 30.0, retries=1)

        mock_uniform.assert_called_once_with(0.0, 0.5)
        assert mock_sleep.call_count == 1

    def test_backoff_caps_grow_then_capped(self, mock_urlopen, mock_sleep, mock_uniform):
        mock_uniform.side_effect = lambda _lo, hi: hi  # sleep the full cap
        mock_urlopen.side_effect = make_status_error(429)

        with pytest.raises(ProviderRequestError):
            post_json(ENDPOINT, {}, HEADERS, 30.0, retries=5)

        assert [call.args[0] for call in mock_sleep.call_args_list] == [
            0.5,
            1.0,
            2.0,
            4.0,
            8.0,
        ]


@patch("nexusagent.http_provider.random.uniform", return_value=0.0)
@patch("nexusagent.http_provider.time.sleep")
@patch("nexusagent.http_provider.urllib.request.urlopen")
class TestPostSseRetries:
    def test_retries_before_headers_then_streams(self, mock_urlopen, mock_sleep, _mock_uniform):
        stream = MagicMock()
        stream.__iter__.return_value = iter([b"data: hello\n\n"])
        mock_urlopen.side_effect = [make_status_error(503), stream]

        events = list(post_sse(ENDPOINT, {}, HEADERS, 30.0, retries=1))

        assert events == ["hello"]
        assert mock_urlopen.call_count == 2
        assert mock_sleep.call_count == 1

    def test_mid_stream_failure_is_not_retried(self, mock_urlopen, mock_sleep, _mock_uniform):
        stream = MagicMock()
        stream.__iter__.side_effect = http.client.IncompleteRead(b"partial")
        mock_urlopen.return_value = stream

        iterator = post_sse(ENDPOINT, {}, HEADERS, 30.0, retries=3)

        with pytest.raises(ProviderRequestError, match="stream failed"):
            list(iterator)

        assert mock_urlopen.call_count == 1
        assert mock_sleep.call_count == 0


class TestProviderWiring:
    @patch("nexusagent.http_provider.time.sleep")
    @patch("nexusagent.http_provider.urllib.request.urlopen")
    def test_http_provider_retries_from_config(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            make_status_error(429),
            make_status_error(500),
            make_response({"output": "hello"}),
        ]
        provider = HttpProvider(ProviderConfig(endpoint=ENDPOINT, retries=2))

        assert provider.generate("hi") == "hello"
        assert mock_urlopen.call_count == 3
        assert mock_sleep.call_count == 2

    def test_http_provider_negative_retries_fail_fast(self):
        provider = HttpProvider(ProviderConfig(endpoint=ENDPOINT, retries=-1))

        with pytest.raises(ProviderConfigurationError, match="non-negative"):
            provider.generate("hi")

    @patch("nexusagent.openai_provider.post_json")
    def test_openai_provider_passes_retries(self, mock_post_json):
        mock_post_json.return_value = {"choices": [{"message": {"content": "hi"}}]}
        provider = OpenAIProvider(ProviderConfig(model="m", retries=4))

        provider.generate_response("hi")

        assert mock_post_json.call_args.kwargs["retries"] == 4

    @patch("nexusagent.openai_provider.post_sse")
    def test_openai_streaming_passes_retries(self, mock_post_sse):
        mock_post_sse.return_value = iter(['{"choices": [{"delta": {"content": "hi"}}]}', "[DONE]"])
        provider = OpenAIProvider(ProviderConfig(model="m", retries=4))

        events = list(provider.stream_response("hi"))

        assert events[-1] == TextResponse("hi")
        assert mock_post_sse.call_args.kwargs["retries"] == 4

    def test_openai_negative_retries_fail_fast(self):
        provider = OpenAIProvider(ProviderConfig(model="m", retries=-1))

        with pytest.raises(ProviderConfigurationError, match="non-negative"):
            provider.generate_response("hi")

    @patch("nexusagent.anthropic_provider.post_json")
    def test_anthropic_provider_passes_retries(self, mock_post_json):
        mock_post_json.return_value = {"content": [{"type": "text", "text": "hi"}]}
        provider = AnthropicProvider(ProviderConfig(model="m", retries=3))

        provider.generate_response("hi")

        assert mock_post_json.call_args.kwargs["retries"] == 3

    @patch("nexusagent.anthropic_provider.post_sse")
    def test_anthropic_streaming_passes_retries(self, mock_post_sse):
        mock_post_sse.return_value = iter(
            ['{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}']
        )
        provider = AnthropicProvider(ProviderConfig(model="m", retries=3))

        events = list(provider.stream_response("hi"))

        assert events[-1] == TextResponse("hi")
        assert mock_post_sse.call_args.kwargs["retries"] == 3

    def test_anthropic_negative_retries_fail_fast(self):
        provider = AnthropicProvider(ProviderConfig(model="m", retries=-1))

        with pytest.raises(ProviderConfigurationError, match="non-negative"):
            provider.generate_response("hi")

    @patch("nexusagent.gemini_provider.post_json")
    def test_gemini_provider_passes_retries(self, mock_post_json):
        mock_post_json.return_value = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
        provider = GeminiProvider(ProviderConfig(model="m", retries=5))

        provider.generate_response("hi")

        assert mock_post_json.call_args.kwargs["retries"] == 5

    @patch("nexusagent.gemini_provider.post_sse")
    def test_gemini_streaming_passes_retries(self, mock_post_sse):
        mock_post_sse.return_value = iter(
            ['{"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}']
        )
        provider = GeminiProvider(ProviderConfig(model="m", retries=5))

        events = list(provider.stream_response("hi"))

        assert events[-1] == TextResponse("hi")
        assert mock_post_sse.call_args.kwargs["retries"] == 5

    def test_gemini_negative_retries_fail_fast(self):
        provider = GeminiProvider(ProviderConfig(model="m", retries=-1))

        with pytest.raises(ProviderConfigurationError, match="non-negative"):
            provider.generate_response("hi")


class TestSettingsRetries:
    def test_default_retries(self):
        assert Settings().retries == 2

    def test_from_env_reads_nexus_retries(self, monkeypatch):
        monkeypatch.setenv("NEXUS_RETRIES", "5")

        assert Settings.from_env().retries == 5

    def test_from_env_accepts_zero(self, monkeypatch):
        monkeypatch.setenv("NEXUS_RETRIES", "0")

        assert Settings.from_env().retries == 0

    def test_from_env_rejects_non_integer(self, monkeypatch):
        monkeypatch.setenv("NEXUS_RETRIES", "two")

        with pytest.raises(ValueError, match="NEXUS_RETRIES"):
            Settings.from_env()

    def test_validate_rejects_negative(self):
        with pytest.raises(ValueError, match="negative"):
            Settings(retries=-1).validate()

    def test_repr_includes_retries_and_masks_api_key(self, monkeypatch):
        monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

        repr_text = repr(Settings.from_env())

        assert "super-secret-value" not in repr_text
        assert "retries=2" in repr_text


class TestRuntimeWiring:
    def test_create_runtime_passes_retries_into_provider_config(self, monkeypatch):
        captured: dict = {}

        def fake_create_provider(name, config):
            captured["config"] = config
            from nexusagent.providers import FakeProvider

            return FakeProvider(config)

        monkeypatch.setattr("nexusagent.runtime.create_provider", fake_create_provider)
        settings = Settings(retries=3)

        from nexusagent.runtime import create_runtime

        create_runtime(settings)

        assert captured["config"].retries == 3


class TestProviderConfig:
    def test_default_retries_is_two(self):
        assert ProviderConfig().retries == 2

    def test_retries_is_configurable(self):
        assert ProviderConfig(retries=4).retries == 4
