"""Native per-vendor history threading (ADR 0014), offline.

With conversation memory configured (ADR 0012), providers that opt into
native history threading (ADR 0014) receive the remembered turns as
structured ``(role, text)`` pairs and rehydrate them into their vendor's
native multi-message wire format — instead of the flattened text
transcript every provider saw before 1.5.

This example runs entirely offline: it points the REAL OpenAI adapter at
a local echo backend that records the exact request body, so you can see
the ``messages`` array the library sends — remembered turns first, then
the current user input. The same happens for Anthropic (``messages``)
and Gemini (``contents`` with ``model`` role) adapters.

Run: python examples/native_history.py
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from nexusagent import Agent, InMemoryMemory
from nexusagent.openai_provider import OpenAIProvider
from nexusagent.provider import ProviderConfig

captured: list[dict] = []


class EchoBackend(BaseHTTPRequestHandler):
    """A local stand-in for a Chat Completions server: records and answers."""

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        captured.append(body)
        answer = json.dumps({"choices": [{"message": {"content": "I remember, Sara."}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(answer.encode())

    def log_message(self, *args) -> None:  # keep the example output clean
        pass


def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), EchoBackend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"

    provider = OpenAIProvider(ProviderConfig(model="local-model", endpoint=endpoint))
    agent = Agent(provider, memory=InMemoryMemory())

    agent.run("My name is Sara")
    agent.run("What is my name?")

    print("The OpenAI adapter sent these request bodies:\n")
    for index, body in enumerate(captured, start=1):
        print(f"--- request {index} ---")
        print(json.dumps(body, indent=2))
        print()

    # The second request carries the remembered conversation as REAL
    # messages — this is what changed in 1.5 (before, the transcript was
    # flattened into a single user message):
    second_messages = captured[1]["messages"]
    assert second_messages == [
        {"role": "user", "content": "My name is Sara"},
        {"role": "assistant", "content": "I remember, Sara."},
        {"role": "user", "content": "What is my name?"},
    ]
    print("native history threading confirmed: roles survive the wire.")
    server.shutdown()


if __name__ == "__main__":
    main()
