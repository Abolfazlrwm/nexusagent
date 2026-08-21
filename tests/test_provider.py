import pytest

from nexusagent.provider import Provider, ProviderConfig


class EchoProvider(Provider):
    def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"


def test_concrete_provider_can_be_instantiated():
    provider = EchoProvider()

    assert isinstance(provider, Provider)


def test_generate_returns_expected_string():
    provider = EchoProvider()

    result = provider.generate("hello")

    assert result == "echo: hello"


def test_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Provider()


def test_generate_accepts_a_string_prompt():
    provider = EchoProvider()

    result = provider.generate("some prompt")

    assert isinstance(result, str)


def test_provider_config_stores_model_and_api_key():
    config = ProviderConfig(model="fake-model", api_key="secret")

    assert config.model == "fake-model"
    assert config.api_key == "secret"


def test_provider_config_defaults_to_none():
    config = ProviderConfig()

    assert config.model is None
    assert config.api_key is None


def test_provider_config_is_immutable():
    config = ProviderConfig(model="fake-model")

    with pytest.raises(AttributeError):
        config.model = "changed"


def test_provider_config_repr_does_not_expose_api_key():
    config = ProviderConfig(model="fake-model", api_key="super-secret")

    assert "super-secret" not in repr(config)
    assert "set" in repr(config)
