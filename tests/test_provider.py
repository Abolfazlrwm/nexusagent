import pytest

from nexusagent.provider import Provider


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
