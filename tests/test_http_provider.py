import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from nexusagent.http_provider import HttpProvider
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)


def make_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_http_provider_construction_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("constructing HttpProvider must not connect")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))


def test_http_provider_is_a_provider():
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    assert isinstance(provider, Provider)


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_sends_expected_request(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "hello"})
    config = ProviderConfig(
        model="test-model",
        api_key="secret-key",
        endpoint="https://example.test/generate",
        timeout=5,
    )
    provider = HttpProvider(config)

    provider.generate("hi there")

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://example.test/generate"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("Authorization") == "Bearer secret-key"

    body = json.loads(request.data)
    assert body == {"model": "test-model", "input": "hi there"}

    assert mock_urlopen.call_args.kwargs["timeout"] == 5


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_without_api_key_omits_authorization_header(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "hello"})
    config = ProviderConfig(endpoint="https://example.test/generate", api_key=None)
    provider = HttpProvider(config)

    provider.generate("hi")

    request = mock_urlopen.call_args.args[0]
    assert request.get_header("Authorization") is None


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_returns_output_field(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": "hello world"})
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    result = provider.generate("hi")

    assert result == "hello world"


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_invalid_json_raises(mock_urlopen):
    response = MagicMock()
    response.read.return_value = b"not json"
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    mock_urlopen.return_value = response

    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_missing_output_field_raises(mock_urlopen):
    mock_urlopen.return_value = make_response({"something_else": "value"})
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


def make_raw_response(raw: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = raw
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@pytest.mark.parametrize(
    "raw",
    [
        b'[{"output": "hello"}]',
        b'"hello"',
        b"123",
        b"true",
    ],
)
@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_non_object_response_raises(mock_urlopen, raw):
    mock_urlopen.return_value = make_raw_response(raw)
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("output_value", [None, 123, ["hello"]])
@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_non_string_output_raises(mock_urlopen, output_value):
    mock_urlopen.return_value = make_response({"output": output_value})
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@pytest.mark.parametrize("output_value", ["", "   ", "\n", "\t"])
@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_empty_output_raises(mock_urlopen, output_value):
    mock_urlopen.return_value = make_response({"output": output_value})
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderResponseError):
        provider.generate("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_preserves_surrounding_whitespace_in_output(mock_urlopen):
    mock_urlopen.return_value = make_response({"output": " hello "})
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    result = provider.generate("hi")

    assert result == " hello "


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_http_error_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://example.test/generate", 500, "Internal Server Error", None, None
    )
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503, 504])
@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_http_status_errors_raise_clean_exception(mock_urlopen, status):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://example.test/generate", status, "error", None, None
    )
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderRequestError, match=str(status)):
        provider.generate("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_network_failure_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_timeout_raises_clean_exception(mock_urlopen):
    mock_urlopen.side_effect = TimeoutError()
    provider = HttpProvider(ProviderConfig(endpoint="https://example.test/generate"))

    with pytest.raises(ProviderRequestError):
        provider.generate("hi")


def test_http_provider_missing_endpoint_raises():
    provider = HttpProvider(ProviderConfig())

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_http_provider_invalid_timeout_raises(timeout):
    provider = HttpProvider(
        ProviderConfig(endpoint="https://example.test/generate", timeout=timeout)
    )

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


@pytest.mark.parametrize("timeout", [0, -1])
def test_http_provider_invalid_timeout_does_not_perform_network_access(monkeypatch, timeout):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid timeout must not trigger a network request")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail_if_called)

    provider = HttpProvider(
        ProviderConfig(endpoint="https://example.test/generate", timeout=timeout)
    )

    with pytest.raises(ProviderConfigurationError):
        provider.generate("hi")


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    config = ProviderConfig(endpoint="https://example.test/generate", api_key="super-secret")
    provider = HttpProvider(config)

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret" not in str(exc_info.value)


@patch("nexusagent.http_provider.urllib.request.urlopen")
def test_http_provider_http_error_does_not_leak_api_key(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://example.test/generate", 401, "Unauthorized", None, None
    )
    config = ProviderConfig(endpoint="https://example.test/generate", api_key="super-secret-key")
    provider = HttpProvider(config)

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.generate("hi")

    assert "super-secret-key" not in str(exc_info.value)


def test_http_provider_repr_does_not_leak_api_key():
    config = ProviderConfig(endpoint="https://example.test/generate", api_key="super-secret")
    provider = HttpProvider(config)

    assert "super-secret" not in repr(provider.config)
