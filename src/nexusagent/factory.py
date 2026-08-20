from nexusagent.provider import Provider
from nexusagent.providers import FakeProvider


def create_provider(name: str) -> Provider:
    if name == "fake":
        return FakeProvider()

    raise ValueError(f"Unsupported provider: {name!r}")
