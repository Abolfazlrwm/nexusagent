"""Minimal multi-agent orchestration (ADR 0015).

One prompt in, one named agent out, that agent's own result back —
no graphs, no shared state, no handoff negotiation. The whole feature is
two pieces:

    :class:`AgentTeam` — a non-empty mapping of named
    :class:`~nexusagent.agent.Agent` specialists plus a router callable.
    Every ``run()`` asks the router once which agent should handle the
    prompt, then delegates to that agent unchanged: its own bounded tool
    loop (ADR 0002), its own tools, its own memory (ADR 0012/0013) and
    its own streaming (ADR 0009).

    :func:`create_provider_router` — builds a router callable from any
    :class:`~nexusagent.provider.Provider`: one ``generate()`` call that
    lists the agent names and the user prompt, followed by a documented,
    deterministic parse. A routing decision is one question, not a
    conversation, so the router never runs the tool loop.

Routing is explicit and readable by design: the router is a plain
function the caller can inspect, the agent names are mapping keys, and
:attr:`TeamResult.agent_name` records who answered. Router failures —
an exception or an unknown name — become
``TeamResult(success=False)`` results with the reason in ``output``,
mirroring how :meth:`nexusagent.agent.Agent.run` reports provider
errors instead of crashing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from nexusagent.agent import Agent, AgentResult
from nexusagent.logging import get_logger
from nexusagent.provider import Provider, ProviderResponseError

__all__ = ["AgentTeam", "TeamResult", "create_provider_router"]

DEFAULT_ROUTER_INSTRUCTION = (
    "You are the router of a team of AI agents. Decide which single agent "
    "should handle the user prompt. Answer with exactly one agent name "
    "and nothing else."
)

_logger = get_logger("nexusagent.orchestration")

Router = Callable[[str], str]


@dataclass(frozen=True)
class TeamResult:
    """The result of one team run: who answered and what they said.

    ``output`` and ``success`` mirror :class:`nexusagent.agent.AgentResult`
    field-for-field; ``agent_name`` is the name of the team member that
    produced the answer. It is empty only when routing itself failed and
    no agent was selected.
    """

    output: str
    success: bool
    agent_name: str


class AgentTeam:
    """Route each prompt to one named agent and return that agent's result.

    ``agents`` is a non-empty mapping of non-empty string names to
    :class:`~nexusagent.agent.Agent` instances; ``router`` is a callable
    that receives the raw user input and returns one of those names. Both
    are validated eagerly at construction, like
    :meth:`nexusagent.tool_registry.ToolRegistry.register`.

    The team owns no behavior of its own. The selected agent's bounded
    tool loop, tools, memory and streaming all run unchanged, so a member
    behaves inside the team exactly as it would standalone (ADR 0015).
    """

    def __init__(self, agents: Mapping[str, Agent], router: Router) -> None:
        if not isinstance(agents, Mapping):
            raise TypeError("agents must be a mapping of name -> Agent")

        if not agents:
            raise ValueError("agents must not be empty")

        for name, agent in agents.items():
            if not isinstance(name, str):
                raise TypeError("agent names must be strings")

            if not name.strip():
                raise ValueError("agent names must not be empty or whitespace-only")

            if not isinstance(agent, Agent):
                raise TypeError(f"agent {name!r} must be an Agent instance")

        if not callable(router):
            raise TypeError("router must be callable")

        self._agents: Mapping[str, Agent] = MappingProxyType(dict(agents))
        self._router = router

    @property
    def agents(self) -> Mapping[str, Agent]:
        """A read-only view of the team members, name -> Agent."""
        return self._agents

    def run(self, input_text: str, *, on_delta: Callable[[str], None] | None = None) -> TeamResult:
        """Route ``input_text`` to one member agent and return its result.

        The input is validated exactly like :meth:`nexusagent.agent.Agent.run`
        (TypeError for non-strings, ValueError for empty or whitespace-only
        text). The router is called once with the raw input; ``on_delta`` is
        forwarded to the selected agent unchanged. Routing failures — any
        exception raised by the router, or a name that is not a team
        member — become a ``TeamResult(success=False, agent_name="")`` whose
        ``output`` explains what went wrong.
        """
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string")

        if not input_text.strip():
            raise ValueError("input_text must not be empty or whitespace-only")

        try:
            name = self._router(input_text)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("router failed: %s", exc)
            return TeamResult(output=f"routing error: {exc}", success=False, agent_name="")

        if not isinstance(name, str):
            return TeamResult(
                output=f"routing error: router returned {type(name).__name__}, expected str",
                success=False,
                agent_name="",
            )

        name = name.strip()
        if name not in self._agents:
            return TeamResult(
                output=(
                    f"routing error: router returned {name!r}, "
                    f"which is not a team member (valid: {sorted(self._agents)})"
                ),
                success=False,
                agent_name="",
            )

        _logger.info("router selected agent %r", name)
        result: AgentResult = self._agents[name].run(input_text, on_delta=on_delta)
        return TeamResult(output=result.output, success=result.success, agent_name=name)


def create_provider_router(
    provider: Provider,
    agent_names: Sequence[str],
    *,
    instruction: str = DEFAULT_ROUTER_INSTRUCTION,
) -> Router:
    """Build a router callable from any Provider.

    The returned callable sends one ``generate()`` request that lists the
    agent names and the user prompt, then parses the reply with a
    documented, deterministic rule: an exact match after stripping, then a
    case-insensitive exact match, otherwise the listed name that appears
    earliest in the reply (ties resolve to the earlier listed name). If no
    name appears at all, ``ProviderResponseError`` is raised — the team
    turns that into a failed ``TeamResult``. ``provider.generate()`` may
    also raise its own provider errors; both paths surface as routing
    failures instead of crashing the caller.
    """
    if not isinstance(provider, Provider):
        raise TypeError("provider must be a Provider instance")

    if not isinstance(agent_names, Sequence) or isinstance(agent_names, (str, bytes)):
        raise TypeError("agent_names must be a sequence of strings")

    if not agent_names:
        raise ValueError("agent_names must not be empty")

    for name in agent_names:
        if not isinstance(name, str):
            raise TypeError("agent names must be strings")

        if not name.strip():
            raise ValueError("agent names must not be empty or whitespace-only")

    if len(set(agent_names)) != len(agent_names):
        raise ValueError("agent_names must not contain duplicates")

    listing = "\n".join(f"- {name}" for name in agent_names)

    def router(prompt: str) -> str:
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")

        if not prompt.strip():
            raise ValueError("prompt must not be empty or whitespace-only")

        composed = (
            f"{instruction}\n\nAvailable agents:\n{listing}\n\n"
            f"User prompt:\n{prompt}\n\n"
            "Answer with exactly one agent name and nothing else."
        )
        reply = provider.generate(composed)

        if not isinstance(reply, str):
            raise ProviderResponseError("router provider returned a non-string reply")

        reply = reply.strip()
        lowered = reply.lower()
        for name in agent_names:
            if lowered == name.lower():
                return name

        best_name, best_position = "", len(reply)
        for name in agent_names:
            position = lowered.find(name.lower())
            if position != -1 and position < best_position:
                best_name, best_position = name, position

        if not best_name:
            raise ProviderResponseError(
                f"router provider did not name any of the agents {sorted(agent_names)!r}; "
                f"reply was {reply!r}"
            )

        return best_name

    return router
