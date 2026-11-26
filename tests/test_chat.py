"""The offline chat REPL (ADR 0018): behavior, commands and integration.

``run_chat_repl`` is driven through injected input/output callables, so
every conversation below is deterministic and terminal-free; the CLI
integration test runs the real ``python -m nexusagent chat`` in a
subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from nexusagent.chat import CHAT_MEMORY_TURNS, PS1, build_chat_runtime, run_chat_repl
from nexusagent.demo_provider import DemoProvider
from nexusagent.memory import InMemoryMemory


class ScriptInput:
    """Scripted stdin: returns lines, raises EOF when exhausted."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.index = 0
        self.prompts: list[str] = []

    def __call__(self, prompt: str = "") -> str:
        self.prompts.append(prompt)
        if self.index >= len(self.lines):
            raise EOFError
        line = self.lines[self.index]
        self.index += 1
        return line


class Capture:
    """Scripted stdout: collects every fragment."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def __call__(self, text: str) -> None:
        self.chunks.append(text)

    @property
    def text(self) -> str:
        return "".join(self.chunks)


@pytest.fixture()
def chat_runtime():
    runtime, label = build_chat_runtime()
    return runtime, label


def run_session(lines: list[str], **kwargs: object) -> tuple[Capture, ScriptInput]:
    out = Capture()
    src = ScriptInput(lines)
    run_chat_repl(
        kwargs.pop("runtime"),  # type: ignore[arg-type]
        input_fn=src,  # type: ignore[arg-type]
        output_fn=out,  # type: ignore[arg-type]
        **kwargs,
    )
    return out, src


# -- building the chat runtime ---------------------------------------------


def test_default_chat_runtime_is_the_offline_demo_brain(chat_runtime):
    runtime, label = chat_runtime

    assert isinstance(runtime.agent.provider, DemoProvider)
    assert "offline demo brain" in label
    assert "no API keys" in label


def test_default_chat_memory_is_bounded():
    runtime, _ = build_chat_runtime()
    memory = runtime.memory
    assert isinstance(memory, InMemoryMemory)

    from nexusagent.memory import ConversationTurn

    for i in range(CHAT_MEMORY_TURNS + 5):
        memory.append(ConversationTurn(role="user", text=f"m{i}"))

    assert len(memory.history()) == CHAT_MEMORY_TURNS


def test_provider_flag_builds_the_real_provider_from_env(monkeypatch):
    monkeypatch.setenv("NEXUS_PROVIDER", "openai")
    monkeypatch.setenv("NEXUS_API_KEY", "sk-test")
    monkeypatch.setenv("NEXUS_MODEL", "gpt-test")
    runtime, label = build_chat_runtime("openai")

    assert type(runtime.agent.provider).__name__ == "OpenAIProvider"
    assert "openai provider" in label
    assert runtime.memory is None


def test_unknown_provider_flag_is_rejected_before_any_network_call():
    with pytest.raises(ValueError, match="Unsupported provider"):
        build_chat_runtime("azure")


# -- banner and the REPL loop ------------------------------------------------


def test_banner_names_the_version_and_the_brain(chat_runtime):
    runtime, label = chat_runtime
    out, _ = run_session(["/exit"], runtime=runtime, label=label)

    assert "offline demo brain" in out.text
    assert "/exit quits" in out.text


def test_math_runs_the_real_tool_loop(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["what is 144 / 12?", "/exit"], runtime=runtime)

    assert "144 / 12 equals 12." in out.text


def test_name_memory_works_across_turns(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["my name is Sara", "what is my name?", "/exit"], runtime=runtime)

    assert "Nice to meet you, Sara!" in out.text
    assert "Your name is Sara" in out.text


def test_streamed_output_still_contains_the_full_answer(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["what is 144 / 12?", "/exit"], runtime=runtime)

    assert "144 / 12 equals 12." in out.text


def test_no_stream_prints_the_whole_answer(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["what is 144 / 12?", "/exit"], runtime=runtime, stream=False)

    assert "144 / 12 equals 12." in out.text


def test_unknown_question_gets_the_honest_fallback(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["explain jazz fusion", "/exit"], runtime=runtime)

    assert "DemoProvider" in out.text


def test_empty_lines_are_ignored_without_provider_calls(chat_runtime):
    runtime, _ = chat_runtime
    calls_before = runtime.agent.provider.calls
    out, src = run_session(["", "   ", "/exit"], runtime=runtime)

    assert runtime.agent.provider.calls == calls_before
    assert len(src.prompts) == 3
    assert "goodbye" in out.text


# -- the commands ------------------------------------------------------------


def test_help_lists_the_commands(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["/help", "/exit"], runtime=runtime)

    assert "/reset" in out.text
    assert "/tools" in out.text
    assert "/exit" in out.text


def test_reset_clears_the_conversation_memory(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(
        ["my name is Sara", "/reset", "what is my name?", "/exit"], runtime=runtime
    )

    assert "memory cleared" in out.text
    assert "don't know" in out.text


def test_reset_without_memory_is_honest(monkeypatch):
    monkeypatch.setenv("NEXUS_PROVIDER", "fake")
    runtime, _ = build_chat_runtime("fake")

    assert runtime.memory is None
    out, _ = run_session(["/reset", "/exit"], runtime=runtime)

    assert "nothing to reset" in out.text


def test_tools_lists_the_registered_tools(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session(["/tools", "/exit"], runtime=runtime)

    assert "calculator" in out.text
    assert "echo" in out.text


def test_exit_quits_without_reading_further_lines(chat_runtime):
    runtime, _ = chat_runtime
    out, src = run_session(["/exit", "SHOULD-NOT-BE-READ"], runtime=runtime)

    assert src.index == 1
    assert "goodbye" in out.text


def test_quit_is_an_alias_of_exit(chat_runtime):
    runtime, _ = chat_runtime
    out, src = run_session(["/quit"], runtime=runtime)

    assert src.index == 1
    assert "goodbye" in out.text


def test_eof_ends_the_session_gracefully(chat_runtime):
    runtime, _ = chat_runtime
    out, _ = run_session([], runtime=runtime)

    assert "goodbye" in out.text


def test_keyboard_interrupt_ends_the_session_gracefully(chat_runtime):
    runtime, _ = chat_runtime

    def interrupting_input(prompt: str = "") -> str:
        raise KeyboardInterrupt

    out = Capture()
    run_chat_repl(runtime, input_fn=interrupting_input, output_fn=out)

    assert "goodbye" in out.text


def test_prompt_is_passed_to_the_input_function(chat_runtime):
    runtime, _ = chat_runtime
    _, src = run_session(["/exit"], runtime=runtime)

    assert src.prompts == [PS1]


# -- CLI integration (the real entrypoint) ------------------------------------


def run_cli_chat(stdin_text: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nexusagent", "chat", *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )


def test_cli_chat_help_and_exit_round_trip():
    result = run_cli_chat("/help\n/exit\n")

    assert result.returncode == 0
    assert "/reset" in result.stdout
    assert "goodbye" in result.stdout


def test_cli_chat_no_stream_answers_math():
    result = run_cli_chat("what is 144 / 12?\n/exit\n", "--no-stream")

    assert result.returncode == 0
    assert "144 / 12 equals 12." in result.stdout


def test_cli_chat_unknown_provider_fails_with_a_clear_error():
    result = run_cli_chat("/exit\n", "--provider", "azure")

    assert result.returncode == 1
    assert "Unsupported provider" in result.stderr
