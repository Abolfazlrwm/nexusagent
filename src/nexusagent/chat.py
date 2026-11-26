"""The offline chat REPL (ADR 0018).

``nexusagent chat`` turns the runtime into a terminal conversation: a
read-eval-print loop over the real :class:`~nexusagent.runtime.Runtime` —
bounded tool loop, conversation memory (ADR 0012) and streaming
(ADR 0009) — so the library can be *felt* in ten seconds:

    pip install nexusagent-runtime
    nexusagent chat

The default brain is the shipped :class:`~nexusagent.demo_provider.DemoProvider`
(ADR 0016/0017): deterministic, zero API keys, zero network — math runs
the calculator tool, your name is remembered across turns, and a small
fact sheet answers chess, color and science questions. ``--provider
openai|anthropic|gemini|http|fake`` swaps in a real provider configured
from the same ``NEXUS_*`` environment the one-shot ``nexusagent`` command
reads.

The REPL is a thin, testable loop: :func:`run_chat_repl` takes the
input and output callables, so tests drive whole conversations without
a terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

import nexusagent
from nexusagent.agent import Agent
from nexusagent.application import create_application_runtime
from nexusagent.config import Settings
from nexusagent.demo_provider import DemoProvider
from nexusagent.memory import InMemoryMemory
from nexusagent.runtime import Runtime
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_factory import create_tool_registry

__all__ = ["CHAT_MEMORY_TURNS", "PS1", "build_chat_runtime", "run_chat_repl"]

CHAT_MEMORY_TURNS = 16
PS1 = "you> "

_HELP_TEXT = (
    "Commands:\n"
    "  /help   show this help\n"
    "  /reset  clear the conversation memory\n"
    "  /tools  list the registered tools\n"
    "  /exit   leave the chat (also: /quit, Ctrl+D, Ctrl+C)"
)

_GOODBYE = "goodbye — the chat restarts fresh whenever you run `nexusagent chat`."


class _OutputFn(Protocol):
    """Anything print-like: takes a string fragment, returns nothing."""

    def __call__(self, text: str) -> None: ...


def _print_output(text: str) -> None:
    print(text, end="", flush=True)


def build_chat_runtime(provider: str | None = None) -> tuple[Runtime, str]:
    """Build the chat :class:`Runtime` and a human label for the banner.

    With no ``provider`` the shipped offline demo brain answers — the
    same brain the browser demo uses. With ``--provider NAME`` the
    runtime is built from the ``NEXUS_*`` environment exactly like the
    one-shot command; configuration problems raise ``ValueError`` or
    :class:`~nexusagent.provider.ProviderConfigurationError` before any
    network call.
    """
    if provider is None:
        agent = Agent(
            DemoProvider(),
            tool_registry=create_tool_registry(),
            tool_executor=ToolExecutor(),
            memory=InMemoryMemory(max_turns=CHAT_MEMORY_TURNS),
        )
        runtime = Runtime(
            agent,
            tool_registry=agent.tool_registry,
            tool_executor=agent.tool_executor,
        )
        label = "the offline demo brain — deterministic, no API keys, no network"
        return runtime, label

    settings = replace(Settings.from_env(), provider=provider)
    settings.validate()
    return (
        create_application_runtime(settings),
        f"the {provider} provider — configured from the NEXUS_* environment",
    )


def run_chat_repl(
    runtime: Runtime,
    *,
    label: str = "the offline demo brain — deterministic, no API keys, no network",
    input_fn: Callable[[str], str] = input,
    output_fn: _OutputFn = _print_output,
    ps1: str = PS1,
    stream: bool = True,
) -> None:
    """Read prompts, run them through ``runtime``, print answers.

    Each answer streams word by word through ``on_delta`` (ADR 0009)
    unless ``stream`` is off. ``/help``, ``/reset``, ``/tools``, ``/exit``
    and ``/quit`` are handled locally; EOF and ``KeyboardInterrupt`` end
    the session gracefully. The whole conversation lives in the
    runtime's shared memory, so follow-up questions see earlier turns.
    """
    output_fn(f"NexusAgent {nexusagent.__version__} chat — {label}\n")
    output_fn("Type a prompt and press Enter. /help shows commands, /exit quits.\n\n")

    streamed = False

    def _print_delta(delta: str) -> None:
        nonlocal streamed
        streamed = True
        output_fn(delta)

    while True:
        try:
            line = input_fn(ps1).strip()
        except (EOFError, KeyboardInterrupt):
            output_fn(f"\n{_GOODBYE}\n")
            return

        if not line:
            continue

        if line in ("/exit", "/quit"):
            output_fn(f"{_GOODBYE}\n")
            return

        if line == "/help":
            output_fn(f"{_HELP_TEXT}\n\n")
            continue

        if line == "/reset":
            memory = runtime.memory
            if memory is None:
                output_fn("no memory is configured in this session — nothing to reset\n\n")
            else:
                memory.clear()
                output_fn("memory cleared — the conversation starts fresh\n\n")
            continue

        if line == "/tools":
            for tool in runtime.list_tools():
                output_fn(f"{tool.name} — {tool.description}\n")
            output_fn("\n")
            continue

        streamed = False
        result = runtime.run(line, on_delta=_print_delta if stream else None)
        if streamed:
            output_fn("\n")
        if not result.success:
            output_fn(f"error: {result.output}\n")
        elif not streamed:
            output_fn(f"{result.output}\n")
        output_fn("\n")
