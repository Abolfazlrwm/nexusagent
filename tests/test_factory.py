import pytest

from nexusagent.anthropic_provider import AnthropicProvider
from nexusagent.factory import create_provider
from nexusagent.http_provider import HttpProvider
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.provider import Provider, ProviderConfig, ProviderConfigurationError
from nexusagent.providers import FakeProvider


def test_create_provider_fake_returns_fake_provider():
    provider = create_provider("fake")

    assert isinstance(provider, FakeProvider)


def test_create_provider_returns_a_provider():
    provider = create_provider("fake")

    assert isinstance(provider, Provider)


def test_create_provider_unsupported_name_raises_provider_configuration_error():
    with pytest.raises(ProviderConfigurationError):
        create_provider("unknown")


def test_create_provider_error_message_identifies_provider():
    with pytest.raises(ProviderConfigurationError, match="unknown"):
        create_provider("unknown")


def test_create_provider_passes_config_to_provider():
    config = ProviderConfig(model="fake-model", api_key=None)

    provider = create_provider("fake", config)

    assert provider.config is config


def test_create_provider_passes_config_to_http_provider():
    config = ProviderConfig(endpoint="https://example.test")

    provider = create_provider("http", config)

    assert provider.config is config


def test_create_provider_http_returns_http_provider():
    provider = create_provider("http", ProviderConfig(endpoint="https://example.test"))

    assert isinstance(provider, HttpProvider)


def test_create_provider_openai_returns_openai_provider():
    provider = create_provider("openai", ProviderConfig(model="test-model"))

    assert isinstance(provider, OpenAIProvider)


def test_create_provider_passes_config_to_openai_provider():
    config = ProviderConfig(model="test-model")

    provider = create_provider("openai", config)

    assert provider.config is config


def test_create_provider_openai_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_provider() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_provider("openai", ProviderConfig(model="test-model"))


def test_create_provider_anthropic_returns_anthropic_provider():
    provider = create_provider("anthropic", ProviderConfig(model="test-model"))

    assert isinstance(provider, AnthropicProvider)


def test_create_provider_passes_config_to_anthropic_provider():
    config = ProviderConfig(model="test-model")

    provider = create_provider("anthropic", config)

    assert provider.config is config


def test_create_provider_anthropic_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_provider() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_provider("anthropic", ProviderConfig(model="test-model"))


def test_create_provider_does_not_validate_http_config_contents():
    provider = create_provider("http", ProviderConfig())

    assert isinstance(provider, HttpProvider)


def test_create_provider_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_provider() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    create_provider("http", ProviderConfig(endpoint="https://example.test"))


def test_create_provider_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("create_provider() must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    create_provider("http", ProviderConfig(endpoint="https://example.test"))
