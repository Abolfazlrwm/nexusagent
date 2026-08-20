"""Agent Core contract for NexusAgent.

Defines the minimal contract for running an agent: input text in,
an AgentResult out. This does not connect to any LLM or external
service — it establishes the shape future implementations will fill.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentResult:
    """The result of a single agent run."""

    output: str
    success: bool


class Agent:
    """Minimal agent contract.

    This base implementation performs no reasoning and does not call
    any LLM or external service. It exists to establish the run()
    contract that future, real agent implementations will fulfill.
    """

    def run(self, input_text: str) -> AgentResult:
        """Run the agent on the given input and return an AgentResult."""
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        # Deterministic placeholder only — no LLM/provider is called here.
        # A real execution mechanism will replace this in a future task.
        output = f"[placeholder] received: {input_text}"
        return AgentResult(output=output, success=True)
