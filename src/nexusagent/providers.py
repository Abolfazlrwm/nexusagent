from __future__ import annotations

from nexusagent.provider import Provider, ProviderConfig


class FakeProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        return f"fake response: {prompt}"
