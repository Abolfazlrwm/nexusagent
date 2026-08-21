import pytest

from nexusagent.factory import create_provider
from nexusagent.provider import Provider, ProviderConfig
from nexusagent.providers import FakeProvider


def test_create_provider_fake_returns_fake_provider():
    provider = create_provider("fake")

    assert isinstance(provider, FakeProvider)


def test_create_provider_returns_a_provider():
    provider = create_provider("fake")

    assert isinstance(provider, Provider)


def test_create_provider_unsupported_name_raises_value_error():
    with pytest.raises(ValueError):
        create_provider("unknown")


def test_create_provider_error_message_identifies_provider():
    with pytest.raises(ValueError, match="unknown"):
        create_provider("unknown")


def test_create_provider_passes_config_to_provider():
    config = ProviderConfig(model="fake-model", api_key=None)

    provider = create_provider("fake", config)

    assert provider.config is config
