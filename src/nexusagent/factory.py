from nexusagent.anthropic_provider import AnthropicProvider
from nexusagent.http_provider import HttpProvider
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.provider import Provider, ProviderConfig, ProviderConfigurationError
from nexusagent.providers import FakeProvider


def create_provider(name: str, config: ProviderConfig | None = None) -> Provider:
    if name == "fake":
        return FakeProvider(config)

    if name == "http":
        return HttpProvider(config)

    if name == "openai":
        return OpenAIProvider(config)

    if name == "anthropic":
        return AnthropicProvider(config)

    raise ProviderConfigurationError(f"Unsupported provider: {name!r}")
