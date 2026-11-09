"""Use the `http` provider against a local backend - no API key, no internet.

This starts a tiny HTTP server that speaks the NexusAgent wire format
(see docs/protocol.md) on 127.0.0.1, then runs the agent with the `http`
provider. The backend answers in plain text, which proves the provider's
request/response contract works end to end.

Run:
    python examples/http_provider_local.py
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from nexusagent import Settings, create_runtime


class LocalBackend(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        response = {"output": f"backend received: {body['input']}"}
        payload = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # keep the demo output clean
        pass


@contextmanager
def local_backend() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), LocalBackend)  # port 0 = pick a free one
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/generate"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def main() -> None:
    with local_backend() as endpoint:
        settings = Settings(provider="http", endpoint=endpoint, timeout=5.0)
        runtime = create_runtime(settings)

        result = runtime.run("Hello, local backend!")
        print("success:", result.success)
        print("output: ", result.output)

        assert result.success
        assert result.output == "backend received: Hello, local backend!"
        print("OK - the http provider spoke the NexusAgent wire format end to end")


if __name__ == "__main__":
    main()
