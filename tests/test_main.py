import os
import subprocess
import sys

import pytest

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


def test_cli_with_valid_input_stderr_is_empty():
    result = run_cli("Hello NexusAgent")

    assert result.stderr == ""


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


def test_cli_provider_request_failure_exits_nonzero(monkeypatch, capsys):
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexusagent", "--provider", "http", "Hello"],
    )
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_cli_provider_request_failure_prints_clean_error_to_stderr(monkeypatch, capsys):
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexusagent", "--provider", "http", "Hello"],
    )
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert captured.err.strip() != ""


def test_cli_provider_request_failure_does_not_leak_api_key(monkeypatch, capsys):
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nexusagent", "--provider", "http", "Hello"],
    )
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")
    monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "super-secret-value" not in captured.out
    assert "super-secret-value" not in captured.err


def test_cli_real_provider_request_failure_exits_nonzero_via_subprocess():
    # Port 1 is a reserved low port nothing listens on locally, so this
    # fails fast with "connection refused" without touching the network.
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "http://127.0.0.1:1"})

    assert result.returncode != 0


def test_cli_real_provider_request_failure_prints_clean_error_via_subprocess():
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "http://127.0.0.1:1"})

    assert "Traceback" not in result.stderr
    assert result.stderr.strip() != ""


def test_cli_real_provider_request_failure_does_not_leak_api_key_via_subprocess():
    result = run_cli(
        "--provider",
        "http",
        "Hello",
        env={"NEXUS_ENDPOINT": "http://127.0.0.1:1", "NEXUS_API_KEY": "super-secret-value"},
    )

    assert "super-secret-value" not in result.stdout
    assert "super-secret-value" not in result.stderr


def test_cli_real_provider_request_failure_stdout_does_not_contain_error():
    result = run_cli("--provider", "http", "Hello", env={"NEXUS_ENDPOINT": "http://127.0.0.1:1"})

    assert result.stdout == ""


def test_cli_http_response_validation_failure_exits_nonzero(monkeypatch):
    class InvalidJsonResponse:
        def read(self):
            return b"not valid json"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(*args, **kwargs):
        return InvalidJsonResponse()

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "--provider", "http", "Hello"])
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_cli_http_response_validation_failure_prints_clean_error(monkeypatch, capsys):
    class InvalidJsonResponse:
        def read(self):
            return b"not valid json"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(*args, **kwargs):
        return InvalidJsonResponse()

    monkeypatch.setattr("nexusagent.http_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "--provider", "http", "Hello"])
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert captured.err.strip() != ""
    assert captured.out == ""


# --- Tool CLI (Task 1.26) ---


def test_tool_run_echo_prints_output_to_stdout():
    result = run_cli("tool", "run", "echo", "hello world")

    assert result.stdout.strip() == "hello world"


def test_tool_run_echo_exits_zero():
    result = run_cli("tool", "run", "echo", "hello world")

    assert result.returncode == 0


def test_tool_run_echo_stderr_is_empty():
    result = run_cli("tool", "run", "echo", "hello world")

    assert result.stderr == ""


def test_tool_run_delegates_through_runtime_execute_tool(monkeypatch):
    calls = {}

    from nexusagent.runtime import Runtime

    original_execute_tool = Runtime.execute_tool

    def spy_execute_tool(self, tool_name, input_data):
        calls["tool_name"] = tool_name
        calls["input_data"] = input_data
        return original_execute_tool(self, tool_name, input_data)

    monkeypatch.setattr(Runtime, "execute_tool", spy_execute_tool)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "echo", "hello"])

    main()

    assert calls == {"tool_name": "echo", "input_data": "hello"}


def test_tool_run_missing_tool_exits_nonzero():
    result = run_cli("tool", "run", "does-not-exist", "hello")

    assert result.returncode != 0


def test_tool_run_missing_tool_prints_clean_stderr_no_stdout():
    result = run_cli("tool", "run", "does-not-exist", "hello")

    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert result.stderr.strip() != ""


def test_tool_run_execution_failure_exits_nonzero_and_clean(monkeypatch):
    from nexusagent.tool import Tool
    from nexusagent.tool_registry import ToolRegistry

    class FailingTool(Tool):
        def execute(self, input_data: str) -> str:
            raise RuntimeError("tool failed")

    def fake_build_tool_runtime():
        from nexusagent.runtime import create_runtime
        from nexusagent.tool_executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(FailingTool(name="failing", description="Fails"))
        return create_runtime(tool_registry=registry, tool_executor=ToolExecutor())

    monkeypatch.setattr("nexusagent.main._build_tool_runtime", fake_build_tool_runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "failing", "hello"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code != 0


def test_tool_run_execution_failure_prints_clean_error(monkeypatch, capsys):
    from nexusagent.tool import Tool
    from nexusagent.tool_registry import ToolRegistry

    class FailingTool(Tool):
        def execute(self, input_data: str) -> str:
            raise RuntimeError("tool failed")

    def fake_build_tool_runtime():
        from nexusagent.runtime import create_runtime
        from nexusagent.tool_executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(FailingTool(name="failing", description="Fails"))
        return create_runtime(tool_registry=registry, tool_executor=ToolExecutor())

    monkeypatch.setattr("nexusagent.main._build_tool_runtime", fake_build_tool_runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "failing", "hello"])

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "tool failed" in captured.err


def test_tool_run_empty_input_is_rejected():
    result = run_cli("tool", "run", "echo", "")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_tool_run_whitespace_only_input_is_rejected():
    result = run_cli("tool", "run", "echo", "   ")

    assert result.returncode != 0
    assert result.stdout == ""


def test_tool_subcommand_without_run_exits_nonzero_with_usage_error():
    result = run_cli("tool")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_tool_run_without_arguments_exits_nonzero_with_usage_error():
    result = run_cli("tool", "run")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_tool_unknown_subcommand_exits_nonzero_with_usage_error():
    result = run_cli("tool", "unknown", "hello")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_tool_run_does_not_leak_api_key_on_missing_tool():
    result = run_cli(
        "tool", "run", "does-not-exist", "hello", env={"NEXUS_API_KEY": "super-secret-value"}
    )

    assert "super-secret-value" not in result.stdout
    assert "super-secret-value" not in result.stderr


def test_tool_run_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("tool run must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "echo", "hello"])

    main()


def test_tool_run_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("tool run must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "echo", "hello"])

    main()


def test_tool_run_works_without_any_nexus_environment_variables(monkeypatch, capsys):
    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "run", "echo", "hello"])

    main()

    captured = capsys.readouterr()
    assert captured.out.strip() == "hello"


def test_tool_run_multiple_calls_do_not_corrupt_each_other():
    result1 = run_cli("tool", "run", "echo", "first")
    result2 = run_cli("tool", "run", "echo", "second")

    assert result1.stdout.strip() == "first"
    assert result2.stdout.strip() == "second"


def test_existing_agent_cli_still_works_after_tool_command_added():
    result = run_cli("Hello NexusAgent")

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_existing_provider_flag_cli_still_works_after_tool_command_added():
    result = run_cli("--provider", "fake", "Hello NexusAgent")

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_existing_help_cli_still_works_after_tool_command_added():
    result = run_cli("--help")

    assert result.returncode == 0


# --- Tool listing CLI (Task 1.27) ---


def test_tool_list_exits_zero():
    result = run_cli("tool", "list")

    assert result.returncode == 0


def test_tool_list_contains_echo():
    result = run_cli("tool", "list")

    assert "echo" in result.stdout


def test_tool_list_contains_echo_description():
    result = run_cli("tool", "list")

    assert "echo - Returns its input unchanged." in result.stdout.splitlines()


def test_tool_list_stderr_is_empty():
    result = run_cli("tool", "list")

    assert result.stderr == ""


def test_tool_list_no_traceback():
    result = run_cli("tool", "list")

    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_tool_list_preserves_registry_order(monkeypatch, capsys):
    from nexusagent.tool import Tool
    from nexusagent.tool_registry import ToolRegistry

    class EchoTool(Tool):
        def execute(self, input_data: str) -> str:
            return input_data

    def fake_build_tool_runtime():
        from nexusagent.runtime import create_runtime
        from nexusagent.tool_executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(EchoTool(name="echo", description="Echo"))
        registry.register(EchoTool(name="second", description="Second"))
        registry.register(EchoTool(name="third", description="Third"))
        return create_runtime(tool_registry=registry, tool_executor=ToolExecutor())

    monkeypatch.setattr("nexusagent.main._build_tool_runtime", fake_build_tool_runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "echo - Echo",
        "second - Second",
        "third - Third",
    ]


def test_tool_list_empty_registry_exits_zero_with_empty_output(monkeypatch, capsys):
    from nexusagent.tool_registry import ToolRegistry

    def fake_build_tool_runtime():
        from nexusagent.runtime import create_runtime
        from nexusagent.tool_executor import ToolExecutor

        registry = ToolRegistry()
        return create_runtime(tool_registry=registry, tool_executor=ToolExecutor())

    monkeypatch.setattr("nexusagent.main._build_tool_runtime", fake_build_tool_runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_tool_list_never_executes_tools(monkeypatch, capsys):
    from nexusagent.tool import Tool
    from nexusagent.tool_registry import ToolRegistry

    class ExplodingTool(Tool):
        def execute(self, input_data: str) -> str:
            raise AssertionError("tool list must never call execute()")

    def fake_build_tool_runtime():
        from nexusagent.runtime import create_runtime
        from nexusagent.tool_executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(ExplodingTool(name="boom", description="Explodes if executed"))
        return create_runtime(tool_registry=registry, tool_executor=ToolExecutor())

    monkeypatch.setattr("nexusagent.main._build_tool_runtime", fake_build_tool_runtime)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()

    captured = capsys.readouterr()
    assert captured.out.strip() == "boom - Explodes if executed"


def test_tool_list_extra_argument_exits_nonzero():
    result = run_cli("tool", "list", "extra")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_tool_list_does_not_leak_api_key():
    result = run_cli("tool", "list", env={"NEXUS_API_KEY": "super-secret-value"})

    assert "super-secret-value" not in result.stdout
    assert "super-secret-value" not in result.stderr


def test_tool_list_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("tool list must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()


def test_tool_list_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("tool list must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)
    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()


def test_tool_list_works_without_any_nexus_environment_variables(monkeypatch, capsys):
    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(sys, "argv", ["nexusagent", "tool", "list"])

    main()

    captured = capsys.readouterr()
    assert "echo - Returns its input unchanged." in captured.out.splitlines()


def test_tool_run_echo_still_works_after_list_command_added():
    result = run_cli("tool", "run", "echo", "hello world")

    assert result.returncode == 0
    assert result.stdout.strip() == "hello world"


def test_existing_agent_cli_still_works_after_list_command_added():
    result = run_cli("Hello NexusAgent")

    assert result.returncode == 0
    assert result.stdout.strip() == "fake response: Hello NexusAgent"


def test_existing_provider_flag_cli_still_works_after_list_command_added():
    result = run_cli("--provider", "fake", "Hello NexusAgent")

    assert result.returncode == 0


def test_tool_command_without_subcommand_still_fails_cleanly():
    result = run_cli("tool")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_tool_unknown_subcommand_still_fails_cleanly():
    result = run_cli("tool", "unknown")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
