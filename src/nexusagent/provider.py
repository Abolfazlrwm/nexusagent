"""Provider contract for NexusAgent.

A Provider turns a conversation into a model response. Two entry points exist:

* ``generate(prompt) -> str`` -- the original, minimal text-in/text-out contract.
* ``respond(messages, tools) -> ProviderResponse`` -- the structured contract used
  by the agent loop. A response is either a ``TextResponse`` (final answer) or a
  ``ToolCallRequest`` (the model wants a tool to be run).

``respond`` has a default implementation that delegates to ``generate``, so a
provider only implementing ``generate`` keeps working unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class ProviderConfig:
    model: str | None = None
    api_key: str | None = None
    endpoint: str | None = None
    timeout: float = 30.0

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"ProviderConfig(model={self.model!r}, api_key={api_key_display}, "
            f"endpoint={self.endpoint!r}, timeout={self.timeout!r})"
        )


@dataclass(frozen=True)
class TextResponse:
    """A plain text response from a Provider."""

    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """A request from a Provider to call a specific Tool.

    ``call_id`` is the identifier assigned by the backend (if any). It is echoed
    back on the matching tool-result message so backends can pair the two.
    """

    tool_name: str
    tool_input: str
    call_id: str | None = None


ProviderResponse = TextResponse | ToolCallRequest
"""What ``Provider.respond`` returns: a final text answer or a tool-call request."""


@dataclass(frozen=True)
class ToolSpec:
    """What a Provider is told about an available Tool."""

    name: str
    description: str


MESSAGE_ROLES = ("system", "user", "assistant", "tool")


@dataclass(frozen=True)
class Message:
    """One entry of a conversation.

    Roles:

    * ``system``    -- instructions for the model (``content``).
    * ``user``      -- user input (``content``).
    * ``assistant`` -- a text answer (``content``), or, when ``tool_call`` is set,
      the model's request to run a tool.
    * ``tool``      -- the result of running a tool (``content``); ``tool_call``
      is the request this result answers.
    """

    role: str
    content: str = ""
    tool_call: ToolCallRequest | None = None

    def __post_init__(self) -> None:
        if self.role not in MESSAGE_ROLES:
            raise ValueError(f"Invalid message role: {self.role!r}")

        if not isinstance(self.content, str):
            raise TypeError("Message content must be a string")

        if self.role == "tool" and self.tool_call is None:
            raise ValueError("A 'tool' message requires the tool_call it answers")

        if self.tool_call is not None and self.role not in ("assistant", "tool"):
            raise ValueError("tool_call is only valid on 'assistant' and 'tool' messages")


def last_user_text(messages: Sequence[Message]) -> str:
    """Return the content of the most recent user message."""
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    raise ValueError("messages must contain at least one user message")


class Provider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    def respond(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec] = ()
    ) -> ProviderResponse:
        """Return the next response for a conversation.

        The default implementation ignores history and tools and answers the most
        recent user message through ``generate``. Providers that support
        multi-turn conversations or tool calling override this method.
        """
        return TextResponse(self.generate(last_user_text(messages)))


class ProviderError(Exception):
    """Base exception for provider-related failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider configuration is invalid for a provider."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request fails."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response is invalid."""
