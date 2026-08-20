from __future__ import annotations

from nexusagent.provider import Provider


class FakeProvider(Provider):
    def generate(self, prompt: str) -> str:
        return f"fake response: {prompt}"
