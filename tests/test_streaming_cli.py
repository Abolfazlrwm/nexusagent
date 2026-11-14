"""Contract tests for the CLI --stream flag (ADR 0009)."""

import sys

import pytest

from nexusagent.agent import AgentResult
from nexusagent.main import main


class _StubRuntime:
    """Runtime double that streams deltas before reporting the final result."""

    def __init__(self, deltas: list[str], output: str, success: bool = True) -> None:
        self._deltas = deltas
        self._output = output
        self._success = success
        self.seen_on_delta = False

    def run(self, input_text: str, *, on_delta=None) -> AgentResult:
        if on_delta is not None:
            for delta in self._deltas:
                on_delta(delta)
            self.seen_on_delta = True
        return AgentResult(output=self._output, success=self._success)


def run_main(monkeypatch, runtime, *argv: str) -> None:
    monkeypatch.setattr("nexusagent.main.create_application_runtime", lambda settings=None: runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", *argv])
    main()


def test_cli_without_stream_prints_the_whole_answer(capsys, monkeypatch):
    runtime = _StubRuntime(deltas=["Hel", "lo"], output="Hello")
    run_main(monkeypatch, runtime, "hi")

    out = capsys.readouterr().out
    assert out == "Hello\n"
    assert runtime.seen_on_delta is False


def test_cli_stream_prints_deltas_live_then_a_single_newline(capsys, monkeypatch):
    runtime = _StubRuntime(deltas=["Hel", "lo"], output="Hello")
    run_main(monkeypatch, runtime, "--stream", "hi")

    out = capsys.readouterr().out
    # The two deltas are printed as they "arrive"; no full-answer repeat.
    assert out == "Hello\n"
    assert runtime.seen_on_delta is True


def test_cli_stream_with_non_streaming_backend_prints_the_answer_once(capsys, monkeypatch):
    runtime = _StubRuntime(deltas=[], output="plain answer")
    run_main(monkeypatch, runtime, "--stream", "hi")

    out = capsys.readouterr().out
    assert out == "plain answer\n"


def test_cli_stream_failure_prints_error_to_stderr(capsys, monkeypatch):
    runtime = _StubRuntime(deltas=["Par"], output="provider error: boom", success=False)
    with pytest.raises(SystemExit) as excinfo:
        run_main(monkeypatch, runtime, "--stream", "hi")

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "provider error: boom" in captured.err


def test_cli_stream_combines_with_provider_option(monkeypatch, capsys):
    runtime = _StubRuntime(deltas=[], output="fake response: hi")
    run_main(monkeypatch, runtime, "--provider", "fake", "--stream", "hi")

    out = capsys.readouterr().out
    assert out == "fake response: hi\n"


def test_cli_invalid_provider_fails_cleanly_in_process(monkeypatch, capsys):
    from nexusagent.config import Settings

    def raise_for(settings=None):
        settings = settings or Settings.from_env()
        settings.validate()
        raise AssertionError("unreachable")

    monkeypatch.setattr("nexusagent.main.create_application_runtime", raise_for)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "--provider", "nope", "hi"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    assert "Unsupported provider" in capsys.readouterr().err
