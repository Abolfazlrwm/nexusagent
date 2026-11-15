"""Async agent core: the bounded tool loop, awaited.

``AsyncAgent`` mirrors the sync ``Agent`` (ADR 0002 semantics) on top of the
``AsyncProvider`` contract (ADR 0006): same ``AgentResult``, same iteration
bound, and the same rule that tool failures become error results instead of
crashing the run. It also mirrors the sync conversation-memory contract
(ADR 0012): remembered turns are composed into the prompt of each run and
successful runs record their turns. The sync ``Agent`` stays unchanged and
first-class; the two loops are deliberately parallel implementations so
neither can break the other (ADR 0006).
"""

from __future__ import annotations

from collections.abc import Callable

from nexusagent.agent import DEFAULT_MAX_ITERATIONS, AgentResult
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.logging import get_logger
from nexusagent.memory import (
    ASSISTANT_ROLE,
    USER_ROLE,
    ConversationTurn,
    Memory,
    compose_prompt,
)
from nexusagent.provider import (
    AsyncProvider,
    ProviderResponse,
    ProviderResponseError,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)
from nexusagent.tool_executor import ToolExecutionError
from nexusagent.tool_registry import ToolRegistry

__all__ = ["AsyncAgent"]

_logger = get_logger("nexusagent.async_agent")


class AsyncAgent:
    """Run the provider/tool loop from a running event loop."""

    def __init__(
        self,
        provider: AsyncProvider,
        tool_registry: ToolRegistry | None = None,
        tool_executor: AsyncToolExecutor | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        memory: Memory | None = None,
    ) -> None:
        if not isinstance(provider, AsyncProvider):
            raise TypeError("AsyncAgent requires an AsyncProvider instance")

        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
            raise TypeError("max_iterations must be an integer")

        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        if memory is not None and not isinstance(memory, Memory):
            raise TypeError("memory must be a Memory instance")

        self.provider = provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.memory = memory

    async def run(
        self, input_text: str, *, on_delta: Callable[[str], None] | None = None
    ) -> AgentResult:
        """Run the agent on the given input and return an ``AgentResult``.

        Semantics mirror the sync ``Agent.run()``: tools are advertised,
        ``ToolCallRequest``s are executed and their results fed back until a
        plain text answer or ``max_iterations`` provider calls.

        With ``on_delta``, the provider's ``stream_response()`` is consumed
        and ``on_delta`` fires with every streamed text fragment as it
        arrives (mirroring the sync contract, including text emitted before
        a tool request); ``AgentResult.output`` still carries only the
        final answer. Without ``on_delta`` the plain awaited
        ``generate_response()`` path is used, unchanged.

        With memory configured (ADR 0012), semantics mirror the sync
        ``Agent.run()`` exactly: remembered turns are composed into the
        prompt of this run and a successful run records
        ``(user, input_text)`` and ``(assistant, output)``; failed runs
        record nothing.
        """
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        can_use_tools = self.tool_registry is not None and self.tool_executor is not None
        tools = self._tool_specs() if can_use_tools else ()
        tool_results: list[ToolResult] = []
        history = self.memory.history() if self.memory is not None else ()
        prompt = compose_prompt(input_text, history)

        for iteration in range(1, self.max_iterations + 1):
            try:
                if on_delta is None:
                    response = await self._ask_provider(prompt, tools, tuple(tool_results))
                else:
                    response = await self._stream_provider_response(
                        prompt, tools, tuple(tool_results), on_delta
                    )
            except Exception as exc:  # noqa: BLE001
                return AgentResult(output=f"provider error: {exc}", success=False)

            if isinstance(response, TextResponse):
                _logger.debug("iteration %d: provider answered with text", iteration)
                self._remember(input_text, response.text)
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
            tool_results.append(await self._run_tool_call(response))

        return AgentResult(
            output=f"agent stopped: exceeded the maximum of {self.max_iterations} iterations",
            success=False,
        )

    async def execute_tool(self, tool_name: str, input_data: str) -> str:
        """Execute a specific, explicitly named tool and return its output."""
        if self.tool_registry is None:
            raise RuntimeError("AsyncAgent requires a ToolRegistry to execute tools")

        if self.tool_executor is None:
            raise RuntimeError("AsyncAgent requires an AsyncToolExecutor to execute tools")

        tool = self.tool_registry.get(tool_name)
        return await self.tool_executor.execute(tool, input_data)

    def has_tool(self, tool_name: str) -> bool:
        """Return whether a tool is currently available through the agent."""
        if self.tool_registry is None:
            raise RuntimeError("AsyncAgent requires a ToolRegistry to check tool availability")

        return self.tool_registry.has(tool_name)

    async def _ask_provider(
        self,
        input_text: str,
        tools: tuple[ToolSpec, ...],
        tool_results: tuple[ToolResult, ...],
    ) -> ProviderResponse:
        response: ProviderResponse = await self.provider.generate_response(
            input_text, tools=tools, tool_results=tool_results
        )
        return response

    async def _stream_provider_response(
        self,
        input_text: str,
        tools: tuple[ToolSpec, ...],
        tool_results: tuple[ToolResult, ...],
        on_delta: Callable[[str], None],
    ) -> ProviderResponse:
        """Collect one streamed provider response, forwarding text deltas.

        Mirrors the sync ``Agent._stream_provider_response()`` over the
        async ``stream_response()`` contract (ADR 0006/0009). A stream that
        ends without a final response is an error.
        """
        async for event in self.provider.stream_response(
            input_text, tools=tools, tool_results=tool_results
        ):
            if isinstance(event, StreamTextDelta):
                on_delta(event.text)
            else:
                return event

        raise ProviderResponseError("provider stream ended without a final response")

    def _remember(self, input_text: str, output: str) -> None:
        """Record one completed exchange in memory, when configured (ADR 0012)."""
        if self.memory is None:
            return

        self.memory.append(ConversationTurn(USER_ROLE, input_text))
        self.memory.append(ConversationTurn(ASSISTANT_ROLE, output))
        _logger.debug("memory now holds %d turns", len(self.memory))

    def _tool_specs(self) -> tuple[ToolSpec, ...]:
        assert self.tool_registry is not None
        return tuple(ToolSpec(t.name, t.description) for t in self.tool_registry.list_tools())

    async def _run_tool_call(self, request: ToolCallRequest) -> ToolResult:
        """Run one requested tool. Failures become error results, never crashes."""
        try:
            output = await self.execute_tool(request.tool_name, request.tool_input)
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
