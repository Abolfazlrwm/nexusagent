"""Watch text arrive fragment-by-fragment through Agent.run(on_delta=...) - no API key.

The provider below streams its answer in small fragments before the final
response, exactly like a real SSE streaming backend does (ADR 0009). The
agent forwards every fragment to the callback as it arrives while the
AgentResult still carries the complete answer. Swap StreamingDemoProvider
for OpenAIProvider / AnthropicProvider / GeminiProvider and the same
callback shows real streamed text.

Run:
    python examples/streaming.py
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from nexusagent import Settings, create_application_runtime
from nexusagent.agent import Agent
from nexusagent.provider import (
    Provider,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolResult,
    ToolSpec,
)
from nexusagent.runtime import Runtime

ANSWER = "Hello! I am NexusAgent, streaming answers fragment by fragment."


class StreamingDemoProvider(Provider):
    """A tiny provider that streams its reply fragment by fragment."""

    def generate(self, prompt: str) -> str:
        return ANSWER

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> Iterator[ProviderStreamEvent]:
        for fragment in ANSWER.split(" ")[:-1]:
            yield StreamTextDelta(fragment + " ")
        yield TextResponse(ANSWER)


def main() -> None:
    # Demo 1: a provider that really streams - on_delta fires per fragment.
    runtime = Runtime(Agent(StreamingDemoProvider()))

    print("Streaming answer fragment by fragment:\n")
    result = runtime.run("Say hello", on_delta=lambda delta: print(delta, end="", flush=True))
    print(f"\n\nfinal answer: {result.output!r} (success={result.success})")

    # Demo 2: a provider without streaming support - on_delta simply never fires
    # and the complete answer comes back as usual.
    plain_runtime = create_application_runtime(Settings(provider="fake"))
    result = plain_runtime.run("Say hello", on_delta=lambda delta: print(delta, end="", flush=True))
    print(f"\nnon-streaming provider -> {result.output!r}")


if __name__ == "__main__":
    main()
