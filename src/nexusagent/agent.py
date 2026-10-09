"""Agent Core for NexusAgent.

An Agent runs a conversation turn against a Provider. When the Provider answers
with a tool-call request, the Agent executes the named tool through its
ToolRegistry/ToolExecutor, feeds the result back to the Provider, and repeats
until the Provider gives a final text answer or ``max_steps`` is reached.

Tool failures (unknown tool, invalid input, a tool raising) are not fatal: they
are reported back to the Provider as the tool result so the model can recover.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from nexusagent.logging import get_logger
from nexusagent.provider import (
    Message,
    Provider,
    ProviderResponse,
    TextResponse,
    ToolCallRequest,
    ToolSpec,
    last_user_text,
)
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry

DEFAULT_MAX_STEPS = 8

_logger = get_logger("nexusagent.agent")


@dataclass(frozen=True)
class AgentStep:
    """One tool invocation performed during an agent run."""

    tool_name: str
    tool_input: str
    tool_output: str
    is_error: bool = False


@dataclass(frozen=True)
class AgentResult:
    """The result of a single agent run.

    ``steps`` lists the tool invocations made on the way to the answer.
    ``messages`` is the conversation after the run (history + this turn, without
    the system prompt); a Conversation uses it to carry context to the next turn.
    """

    output: str
    success: bool
    steps: tuple[AgentStep, ...] = ()
    messages: tuple[Message, ...] = ()


class Agent:
    def __init__(
        self,
        provider: Provider,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        system_prompt: str | None = None,
    ) -> None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int):
            raise TypeError("max_steps must be an integer")

        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")

        if system_prompt is not None:
            if not isinstance(system_prompt, str):
                raise TypeError("system_prompt must be a string")

            if not system_prompt.strip():
                raise ValueError("system_prompt must not be empty or whitespace-only")

        self.provider = provider
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    def run(self, input_text: str, history: Sequence[Message] | None = None) -> AgentResult:
        """Run the agent on the given input and return an AgentResult.

        ``history`` is the earlier part of the conversation (see Conversation).
        """
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        conversation: list[Message] = [*(history or ()), Message("user", input_text)]
        tools = self._tool_specs()
        steps: list[AgentStep] = []

        for _ in range(self.max_steps):
            try:
                response = self._ask(conversation, tools)
            except Exception as exc:  # noqa: BLE001
                return self._failure(f"provider error: {exc}", steps, conversation)

            if isinstance(response, TextResponse):
                conversation.append(Message("assistant", response.text))
                return AgentResult(
                    output=response.text,
                    success=True,
                    steps=tuple(steps),
                    messages=tuple(conversation),
                )

            if not isinstance(response, ToolCallRequest):
                return self._failure(
                    f"provider error: unsupported response type {type(response).__name__!r}",
                    steps,
                    conversation,
                )

            if not tools:
                return self._failure(
                    f"provider requested tool {response.tool_name!r} "
                    "but the agent has no tools configured",
                    steps,
                    conversation,
                )

            request = replace(response, call_id=response.call_id or f"call_{len(steps) + 1}")
            output, is_error = self._run_requested_tool(request)
            steps.append(AgentStep(request.tool_name, request.tool_input, output, is_error))
            _logger.debug(
                "tool call %s(%r) -> %r%s",
                request.tool_name,
                request.tool_input,
                output,
                " [error]" if is_error else "",
            )
            conversation.append(Message("assistant", tool_call=request))
            conversation.append(Message("tool", output, tool_call=request))

        return self._failure(
            f"agent stopped after {self.max_steps} steps without a final answer",
            steps,
            conversation,
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

    # -- internals -----------------------------------------------------------

    def _tool_specs(self) -> tuple[ToolSpec, ...]:
        if self.tool_registry is None or self.tool_executor is None:
            return ()

        return tuple(ToolSpec(t.name, t.description) for t in self.tool_registry.list_tools())

    def _ask(self, conversation: list[Message], tools: tuple[ToolSpec, ...]) -> ProviderResponse:
        messages = conversation
        if self.system_prompt is not None:
            messages = [Message("system", self.system_prompt), *conversation]

        respond = getattr(self.provider, "respond", None)
        if respond is None:
            # Duck-typed provider that only implements the original generate() contract.
            return TextResponse(self.provider.generate(last_user_text(messages)))

        response: ProviderResponse = respond(messages, tools)
        return response

    def _run_requested_tool(self, request: ToolCallRequest) -> tuple[str, bool]:
        """Run a tool the provider asked for. Never raises; errors become results."""
        try:
            return self.execute_tool(request.tool_name, request.tool_input), False
        except KeyError:
            return f"error: unknown tool {request.tool_name!r}", True
        except (TypeError, ValueError, ToolExecutionError) as exc:
            return f"error: {exc}", True

    @staticmethod
    def _failure(output: str, steps: list[AgentStep], conversation: list[Message]) -> AgentResult:
        return AgentResult(
            output=output,
            success=False,
            steps=tuple(steps),
            messages=tuple(conversation),
        )


class Conversation:
    """A multi-turn session: remembers earlier turns and sends them with each run.

    A failed turn is discarded, so one provider error does not poison the history.
    """

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self._messages: list[Message] = []

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._messages)

    def send(self, input_text: str) -> AgentResult:
        result = self.agent.run(input_text, history=self._messages)
        if result.success:
            self._messages = list(result.messages)
        return result

    def reset(self) -> None:
        self._messages = []
