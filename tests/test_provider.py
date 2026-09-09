import pytest

from nexusagent.agent import Agent
from nexusagent.provider import (
    Provider,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequestError,
    ProviderResponseError,
    TextResponse,
    ToolCallRequest,
)


class EchoProvider(Provider):
    def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"


class IncompleteProvider(Provider):
    pass


class FailingProvider(Provider):
    def generate(self, prompt: str) -> str:
        raise RuntimeError("provider failure")


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


def test_incomplete_provider_subclass_cannot_be_instantiated():
    with pytest.raises(TypeError):
        IncompleteProvider()


def test_generate_accepts_a_string_prompt():
    provider = EchoProvider()

    result = provider.generate("some prompt")

    assert isinstance(result, str)


def test_provider_exposes_a_callable_generate_method():
    provider = EchoProvider()

    assert hasattr(provider, "generate")
    assert callable(provider.generate)


def test_concrete_provider_can_be_used_by_agent():
    agent = Agent(EchoProvider())

    result = agent.run("hello")

    assert result.success is True
    assert result.output == "echo: hello"


def test_provider_generate_can_raise_a_normal_exception_unmodified():
    provider = FailingProvider()

    with pytest.raises(RuntimeError, match="provider failure"):
        provider.generate("hello")


def test_concrete_provider_failure_is_converted_by_agent_to_unsuccessful_result():
    agent = Agent(FailingProvider())

    result = agent.run("hello")

    assert result.success is False
    assert result.output == "provider error: provider failure"


def test_provider_config_stores_model_and_api_key():
    config = ProviderConfig(model="fake-model", api_key="secret")

    assert config.model == "fake-model"
    assert config.api_key == "secret"


def test_provider_config_stores_endpoint_and_timeout():
    config = ProviderConfig(endpoint="https://example.test/generate", timeout=5.0)

    assert config.endpoint == "https://example.test/generate"
    assert config.timeout == 5.0


def test_provider_config_defaults_to_none():
    config = ProviderConfig()

    assert config.model is None
    assert config.api_key is None


def test_provider_config_endpoint_and_timeout_defaults():
    config = ProviderConfig()

    assert config.endpoint is None
    assert config.timeout == 30.0


def test_provider_config_is_immutable():
    config = ProviderConfig(model="fake-model")

    with pytest.raises(AttributeError):
        config.model = "changed"


def test_provider_config_supports_value_equality():
    config1 = ProviderConfig(model="fake-model", api_key="secret")
    config2 = ProviderConfig(model="fake-model", api_key="secret")

    assert config1 == config2
    assert config1 is not config2


def test_provider_config_inequality_for_different_values():
    config1 = ProviderConfig(model="fake-model")
    config2 = ProviderConfig(model="different-model")

    assert config1 != config2


def test_provider_config_repr_does_not_expose_api_key():
    config = ProviderConfig(model="fake-model", api_key="super-secret")

    assert "super-secret" not in repr(config)
    assert "set" in repr(config)


def test_provider_error_inherits_from_exception():
    assert issubclass(ProviderError, Exception)


def test_provider_configuration_error_inherits_from_provider_error():
    assert issubclass(ProviderConfigurationError, ProviderError)


def test_provider_request_error_inherits_from_provider_error():
    assert issubclass(ProviderRequestError, ProviderError)


def test_provider_response_error_inherits_from_provider_error():
    assert issubclass(ProviderResponseError, ProviderError)


def test_provider_configuration_error_can_be_caught_as_provider_error():
    with pytest.raises(ProviderError):
        raise ProviderConfigurationError("bad config")


def test_provider_request_error_can_be_caught_as_provider_error():
    with pytest.raises(ProviderError):
        raise ProviderRequestError("request failed")


def test_provider_response_error_can_be_caught_as_provider_error():
    with pytest.raises(ProviderError):
        raise ProviderResponseError("bad response")


# --- Structured Provider response contract ---


def test_text_response_holds_exact_text():
    response = TextResponse(text="hello world")

    assert response.text == "hello world"


def test_tool_call_request_holds_exact_tool_name_and_input():
    request = ToolCallRequest(tool_name="calculator", tool_input="2 + 3")

    assert request.tool_name == "calculator"
    assert request.tool_input == "2 + 3"


def test_text_response_is_immutable():
    response = TextResponse(text="hello")

    with pytest.raises(AttributeError):
        response.text = "changed"


def test_tool_call_request_is_immutable():
    request = ToolCallRequest(tool_name="echo", tool_input="hi")

    with pytest.raises(AttributeError):
        request.tool_name = "changed"


def test_text_response_supports_value_equality():
    assert TextResponse(text="hello") == TextResponse(text="hello")


def test_text_response_inequality_for_different_values():
    assert TextResponse(text="hello") != TextResponse(text="different")


def test_tool_call_request_supports_value_equality():
    request1 = ToolCallRequest(tool_name="echo", tool_input="hi")
    request2 = ToolCallRequest(tool_name="echo", tool_input="hi")

    assert request1 == request2


def test_tool_call_request_inequality_for_different_values():
    request1 = ToolCallRequest(tool_name="echo", tool_input="hi")
    request2 = ToolCallRequest(tool_name="calculator", tool_input="hi")

    assert request1 != request2
