"""Watch NexusAgent's autonomous tool loop end to end - no API key, no internet.

This starts a tiny local "model backend" that speaks the NexusAgent HTTP protocol
(see docs/protocol.md). The backend first asks the agent to run the calculator,
then turns the tool result into a final answer. The agent does the rest by itself.

Run:
    python examples/tool_loop_demo.py
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from nexusagent import Settings, create_application_runtime
from nexusagent.logging import configure_logging


class DemoBackend(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tool_results = body.get("tool_results", [])

        if not tool_results:
            print(f"  backend <- prompt: {body['input']!r}")
            print(f"  backend    tools it may use: {[t['name'] for t in body['tools']]}")
            reply = {"tool_name": "calculator", "tool_input": "1337 * 42"}
            print(f"  backend -> asks for tool: {reply}")
        else:
            result = tool_results[-1]["output"]
            print(f"  backend <- tool result: {result!r}")
            reply = {"output": f"1337 multiplied by 42 is {result}."}
            print(f"  backend -> final answer: {reply}")

        payload = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), DemoBackend)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    configure_logging("INFO")
    logging.getLogger("nexusagent").info("starting demo backend on port %d", server.server_port)

    settings = Settings(provider="http", endpoint=f"http://127.0.0.1:{server.server_port}/")
    runtime = create_application_runtime(settings)

    print("\nAsking the agent: 'What is 1337 times 42?'\n")
    result = runtime.run("What is 1337 times 42?")

    print(f"\nAgent result -> success={result.success}, output={result.output!r}")
    server.shutdown()


if __name__ == "__main__":
    main()
