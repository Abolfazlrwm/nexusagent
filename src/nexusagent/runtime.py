from __future__ import annotations

from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
from nexusagent.factory import create_provider
from nexusagent.provider import ProviderConfig


class Runtime:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def run(self, input_text: str) -> AgentResult:
        return self.agent.run(input_text)


def create_runtime(settings: Settings | None = None) -> Runtime:
    if settings is None:
        settings = Settings.from_env()

    config = ProviderConfig(
        model=settings.model,
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        timeout=settings.timeout,
    )
    provider = create_provider(settings.provider, config)
    agent = Agent(provider)
    return Runtime(agent)
