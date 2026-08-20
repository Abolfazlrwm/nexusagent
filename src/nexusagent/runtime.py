from __future__ import annotations

from nexusagent.agent import Agent, AgentResult
from nexusagent.config import Settings
from nexusagent.factory import create_provider


class Runtime:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def run(self, input_text: str) -> AgentResult:
        return self.agent.run(input_text)


def create_runtime(settings: Settings | None = None) -> Runtime:
    if settings is None:
        settings = Settings.from_env()

    provider = create_provider(settings.provider)
    agent = Agent(provider)
    return Runtime(agent)
