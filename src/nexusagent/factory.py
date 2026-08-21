from nexusagent.provider import Provider, ProviderConfig
from nexusagent.providers import FakeProvider


def create_provider(name: str, config: ProviderConfig | None = None) -> Provider:
    if name == "fake":
        return FakeProvider(config)

    raise ValueError(f"Unsupported provider: {name!r}")
