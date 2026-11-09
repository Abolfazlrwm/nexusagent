"""Agent Core for NexusAgent.

Defines the contract for running an agent: input text in, an AgentResult out.
The Agent delegates generation to a Provider. When it is given a ToolRegistry
and a ToolExecutor it also runs the autonomous tool loop:

    provider responds -> if it asks for a tool, run it -> feed the result back
    -> provider responds again -> ... until it answers in plain text

The loop is bounded by ``max_iterations`` so a misbehaving backend can never
keep the agent running forever. Explicit ``execute_tool()`` remains available.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexusagent.logging import get_logger
from nexusagent.provider import (
    Provider,
    ProviderResponse,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry

DEFAULT_MAX_ITERATIONS = 10

_logger = get_logger("nexusagent.agent")


@dataclass(frozen=True)
class AgentResult:
    """The result of a single agent run."""

    output: str
    success: bool


class Agent:
    def __init__(
        self,
        provider: Provider,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
            raise TypeError("max_iterations must be an integer")

        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        self.provider = provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations

    def run(self, input_text: str) -> AgentResult:
        """Run the agent on the given input and return an AgentResult.

        If the Provider requests tools and this Agent has a ToolRegistry and a
        ToolExecutor, the requested tools are executed and their results are
        fed back to the Provider until it returns a plain text answer or
        ``max_iterations`` provider calls have been made.
        """
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        can_use_tools = self.tool_registry is not None and self.tool_executor is not None
        tools = self._tool_specs() if can_use_tools else ()
        tool_results: list[ToolResult] = []

        for iteration in range(1, self.max_iterations + 1):
            try:
                response = self._ask_provider(input_text, tools, tuple(tool_results))
            except Exception as exc:  # noqa: BLE001
                return AgentResult(output=f"provider error: {exc}", success=False)

            if isinstance(response, TextResponse):
                _logger.debug("iteration %d: provider answered with text", iteration)
                return AgentResult(output=response.text, success=True)

            if not isinstance(response, ToolCallRequest):
                return AgentResult(
                    output=f"provider error: unexpected response type {type(response).__name__}",
                    success=False,
                )

            if not can_use_tools:
                return AgentResult(
                    output=(
                        f"provider requested tool {response.tool_name!r} "
                        "but the agent has no tools configured"
                    ),
                    success=False,
                )

            _logger.info("iteration %d: provider requested tool %r", iteration, response.tool_name)
            tool_results.append(self._run_tool_call(response))

        return AgentResult(
            output=f"agent stopped: exceeded the maximum of {self.max_iterations} iterations",
            success=False,
        )

    def execute_tool(self, tool_name: str, input_data: str) -> str:
        """Execute a specific, explicitly named tool and return its output."""
        if self.tool_registry is None:
            raise RuntimeError("Agent requires a ToolRegistry to execute tools")

        if self.tool_executor is None:
            raise RuntimeError("Agent requires a ToolExecutor to execute tools")

        tool = self.tool_registry.get(tool_name)
        return self.tool_executor.execute(tool, input_data)

    def has_tool(self, tool_name: str) -> bool:
        """Return whether a tool is currently available through the Agent."""
        if self.tool_registry is None:
            raise RuntimeError("Agent requires a ToolRegistry to check tool availability")

        return self.tool_registry.has(tool_name)

    def _ask_provider(
        self,
        input_text: str,
        tools: tuple[ToolSpec, ...],
        tool_results: tuple[ToolResult, ...],
    ) -> ProviderResponse:
        """Ask the provider for its next response.

        Any object with a ``generate(prompt) -> str`` method is accepted as a
        provider; only ones that also define ``generate_response`` can request
        tools.
        """
        generate_response = getattr(self.provider, "generate_response", None)
        if generate_response is None:
            return TextResponse(self.provider.generate(input_text))

        response: ProviderResponse = generate_response(
            input_text, tools=tools, tool_results=tool_results
        )
        return response

    def _tool_specs(self) -> tuple[ToolSpec, ...]:
        assert self.tool_registry is not None
        return tuple(ToolSpec(t.name, t.description) for t in self.tool_registry.list_tools())

    def _run_tool_call(self, request: ToolCallRequest) -> ToolResult:
        """Run one requested tool. Failures become error results, never crashes.

        The Provider (usually a model) is told what went wrong so it can retry
        with better input, pick another tool, or explain the problem.
        """
        try:
            output = self.execute_tool(request.tool_name, request.tool_input)
        except KeyError:
            return self._error_result(request, f"Tool {request.tool_name!r} is not registered")
        except (TypeError, ValueError, ToolExecutionError) as exc:
            return self._error_result(request, str(exc))

        _logger.debug("tool %r succeeded", request.tool_name)
        return ToolResult(request.tool_name, request.tool_input, output)

    @staticmethod
    def _error_result(request: ToolCallRequest, message: str) -> ToolResult:
        _logger.warning("tool %r failed: %s", request.tool_name, message)
        return ToolResult(request.tool_name, request.tool_input, message, is_error=True)
