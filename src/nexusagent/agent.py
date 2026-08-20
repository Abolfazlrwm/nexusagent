"""Agent Core for NexusAgent.

Defines the minimal contract for running an agent: input text in,
an AgentResult out. The Agent delegates generation to a Provider.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexusagent.provider import Provider


@dataclass(frozen=True)
class AgentResult:
    """The result of a single agent run."""

    output: str
    success: bool


class Agent:
    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def run(self, input_text: str) -> AgentResult:
        """Run the agent on the given input and return an AgentResult."""
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        output = self.provider.generate(input_text)
        return AgentResult(output=output, success=True)
