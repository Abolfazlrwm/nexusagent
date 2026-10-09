import io
import json
import logging
import sys
from unittest.mock import MagicMock

import pytest

from nexusagent.main import main

URLOPEN = "nexusagent.http_provider.urllib.request.urlopen"


@pytest.fixture(autouse=True)
def fresh_nexusagent_logger():
    """configure_logging() keeps its handler between calls; start each test clean."""
    logger = logging.getLogger("nexusagent")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


def run_main(monkeypatch, *argv, stdin=None):
    monkeypatch.setattr(sys, "argv", ["nexusagent", *argv])
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    main()


def reply(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


def test_cli_openai_without_model_fails_cleanly(monkeypatch, capsys):
    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, "--provider", "openai", "hi")

    assert info.value.code == 1
    assert "requires a model" in capsys.readouterr().err


def test_cli_model_flag_reaches_the_provider(monkeypatch, capsys):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["body"] = json.loads(request.data)
        return reply({"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(URLOPEN, fake_urlopen)

    run_main(monkeypatch, "--provider", "openai", "--model", "llama3", "hi")

    assert capsys.readouterr().out.strip() == "hello"
    assert seen["body"]["model"] == "llama3"
    assert {t["function"]["name"] for t in seen["body"]["tools"]} == {
        "echo",
        "uppercase",
        "calculator",
    }


def test_cli_runs_a_real_http_tool_loop_and_verbose_logs_steps():
    """Real subprocess + real socket: a local server scripts a tool call, then an answer."""
    import http.server
    import os
    import subprocess
    import threading

    replies = [
        {"tool_name": "calculator", "tool_input": "6 * 7"},
        {"output": "The answer is 42."},
    ]
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(length)))
            body = json.dumps(replies[len(received) - 1]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {**os.environ, "NEXUS_ENDPOINT": f"http://127.0.0.1:{server.server_port}/"}
        result = subprocess.run(
            [sys.executable, "-m", "nexusagent", "--provider", "http", "-v", "6 times 7?"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=30,
        )
    finally:
        server.shutdown()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "The answer is 42."
    assert "calculator('6 * 7')" in result.stderr
    assert received[1]["messages"][-1] == {
        "role": "tool",
        "content": "42",
        "tool_name": "calculator",
        "tool_input": "6 * 7",
        "call_id": "call_1",
    }


@pytest.mark.parametrize("flag", ["0", "101"])
def test_cli_rejects_bad_max_steps(monkeypatch, capsys, flag):
    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, "--max-steps", flag, "hi")

    assert info.value.code == 1
    assert "max_steps" in capsys.readouterr().err


def test_cli_invalid_log_level_fails_cleanly(monkeypatch, capsys):
    monkeypatch.setenv("NEXUS_LOG_LEVEL", "LOUD")

    with pytest.raises(SystemExit) as info:
        run_main(monkeypatch, "hi")

    assert info.value.code == 1
    assert "Invalid log level" in capsys.readouterr().err


def test_chat_remembers_context_and_supports_reset(monkeypatch, capsys):
    sent = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        sent.append([m["content"] for m in body["messages"]])
        return reply({"output": f"answer {len(sent)}"})

    monkeypatch.setattr(URLOPEN, fake_urlopen)
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://x.test/")
    script = "first\n\nsecond\n/reset\nthird\n/exit\nnever reached\n"

    run_main(monkeypatch, "chat", "--provider", "http", stdin=script)

    out = capsys.readouterr().out
    assert "answer 1" in out and "answer 3" in out
    assert sent[1] == ["first", "answer 1", "second"]
    assert sent[2] == ["third"]
    assert len(sent) == 3


def test_chat_reports_errors_and_keeps_going(monkeypatch, capsys):
    calls = iter([reply({"bad": 1}), reply({"output": "fine"})])
    monkeypatch.setattr(URLOPEN, lambda request, timeout: next(calls))
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://x.test/")

    run_main(monkeypatch, "chat", "--provider", "http", stdin="one\ntwo\n")

    captured = capsys.readouterr()
    assert "fine" in captured.out
    assert "nexusagent: error:" in captured.err


def test_chat_ends_cleanly_on_eof(monkeypatch):
    run_main(monkeypatch, "chat", stdin="")
