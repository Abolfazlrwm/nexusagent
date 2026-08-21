from nexusagent.provider import Provider, ProviderConfig
from nexusagent.providers import FakeProvider


def test_fake_provider_is_a_provider():
    provider = FakeProvider()

    assert isinstance(provider, Provider)


def test_fake_provider_generate_is_deterministic():
    provider = FakeProvider()

    first = provider.generate("hello")
    second = provider.generate("hello")

    assert first == second


def test_fake_provider_generate_returns_string_containing_prompt():
    provider = FakeProvider()

    result = provider.generate("hello")

    assert isinstance(result, str)
    assert "hello" in result


def test_fake_provider_generate_returns_expected_string():
    provider = FakeProvider()

    result = provider.generate("hello")

    assert result == "fake response: hello"


def test_fake_provider_does_not_perform_network_calls(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("FakeProvider.generate must not perform network calls")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    provider = FakeProvider()
    provider.generate("hello")


def test_fake_provider_accepts_provider_config():
    config = ProviderConfig(model="fake-model", api_key=None)

    provider = FakeProvider(config)

    assert provider.config is config


def test_fake_provider_generate_deterministic_with_config():
    config = ProviderConfig(model="fake-model", api_key=None)

    provider = FakeProvider(config)

    assert provider.generate("Hello") == "fake response: Hello"
