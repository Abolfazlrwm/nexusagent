import subprocess
import sys

from nexusagent.main import main


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "nexusagent", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_with_valid_input_exits_zero():
    result = run_cli("Hello NexusAgent")

    assert result.returncode == 0


def test_cli_with_valid_input_prints_fake_provider_output():
    result = run_cli("Hello NexusAgent")

    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_cli_without_input_exits_nonzero():
    result = run_cli()

    assert result.returncode != 0


def test_cli_without_input_prints_usage_error():
    result = run_cli()

    assert "usage" in result.stderr.lower()
    assert "input_text" in result.stderr


def test_cli_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("CLI must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "hello"])

    main()
