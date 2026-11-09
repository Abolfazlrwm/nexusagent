"""End-to-end: Agent + HttpProvider + a real local HTTP server speaking the protocol."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from nexusagent import Settings, create_application_runtime


class ModelHandler(BaseHTTPRequestHandler):
    """A tiny fake 'model backend': asks for the calculator once, then answers."""

    requests: ClassVar[list[dict]] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        type(self).requests.append(body)

        if body.get("tool_results"):
            answer = body["tool_results"][-1]["output"]
            reply = {"output": f"The result is {answer}"}
        else:
            reply = {"tool_name": "calculator", "tool_input": "19 + 23"}

        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    ModelHandler.requests = []
    httpd = HTTPServer(("127.0.0.1", 0), ModelHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/"
    httpd.shutdown()
    httpd.server_close()


def test_full_loop_over_real_http(server):
    runtime = create_application_runtime(Settings(provider="http", endpoint=server, timeout=5))

    result = runtime.run("what is 19 + 23?")

    assert result.success is True
    assert result.output == "The result is 42"


def test_backend_sees_tools_then_tool_results(server):
    runtime = create_application_runtime(Settings(provider="http", endpoint=server, timeout=5))

    runtime.run("what is 19 + 23?")

    first, second = ModelHandler.requests
    assert {t["name"] for t in first["tools"]} == {"echo", "uppercase", "calculator"}
    assert "tool_results" not in first
    assert second["tool_results"] == [
        {"tool_name": "calculator", "tool_input": "19 + 23", "output": "42", "is_error": False}
    ]
