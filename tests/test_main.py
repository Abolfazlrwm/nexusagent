import os
import subprocess
import sys

from nexusagent.factory import create_provider
from nexusagent.main import main
from nexusagent.provider import ProviderConfig


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    return subprocess.run(
        [sys.executable, "-m", "nexusagent", *args],
        capture_output=True,
        text=True,
        check=False,
        env=full_env,
    )


def test_cli_with_valid_input_exits_zero():
    result = run_cli("Hello NexusAgent")

    assert result.returncode == 0


def test_cli_with_valid_input_prints_fake_provider_output():
    result = run_cli("Hello NexusAgent")

    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_cli_with_explicit_provider_option():
    result = run_cli("--provider", "fake", "Hello NexusAgent")

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_cli_uses_provider_from_environment():
    result = run_cli("Hello", env={"NEXUS_PROVIDER": "fake"})

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello"


def test_cli_provider_option_overrides_environment():
    result = run_cli("--provider", "fake", "Hello", env={"NEXUS_PROVIDER": "does-not-exist"})

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello"


def test_cli_with_unsupported_provider_exits_nonzero():
    result = run_cli("--provider", "does-not-exist", "Hello")

    assert result.returncode != 0


def test_cli_with_unsupported_provider_prints_clean_error():
    result = run_cli("--provider", "does-not-exist", "Hello")

    assert "Traceback" not in result.stderr
    assert "does-not-exist" in result.stderr


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


def test_cli_does_not_leak_api_key():
    result = run_cli("Hello", env={"NEXUS_API_KEY": "super-secret-value"})

    assert "super-secret-value" not in result.stdout
    assert "super-secret-value" not in result.stderr


def test_cli_help_does_not_perform_network_access():
    result = run_cli("--help")

    assert result.returncode == 0


def test_cli_selecting_http_provider_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("selecting http provider must not connect until generate() runs")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail_if_called)

    create_provider("http", ProviderConfig(endpoint="https://example.test"))


def test_cli_http_provider_without_endpoint_exits_nonzero():
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "", "NEXUS_API_KEY": ""})

    assert result.returncode != 0


def test_cli_http_provider_without_endpoint_prints_clean_error():
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "", "NEXUS_API_KEY": ""})

    assert "Traceback" not in result.stderr


def test_cli_http_provider_invalid_endpoint_scheme_exits_nonzero():
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "ftp://example.test"})

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_cli_configuration_error_does_not_leak_api_key():
    result = run_cli(
        "--provider",
        "http",
        "Hello",
        env={"NEXUS_ENDPOINT": "", "NEXUS_API_KEY": "super-secret-value"},
    )

    assert "super-secret-value" not in result.stdout
    assert "super-secret-value" not in result.stderr
