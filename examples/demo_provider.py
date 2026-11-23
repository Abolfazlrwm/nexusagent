"""The offline demo brain (ADR 0016), end to end.

``DemoProvider`` ships with the runtime so you can run the real Agent —
bounded tool loop, memory, streaming — with zero API keys and zero
network. This example exercises all four tricks deterministically:

    "what color is the sky?"  -> fact-sheet answer (Rayleigh scattering)
    "who start first in chess?" -> knowledge-sheet answer (white moves first)
    "what is 144 / 12?"       -> real tool loop via the calculator tool
    "my name is Sara"         -> recorded by InMemoryMemory (ADR 0012)
    "what is my name?"        -> recovered from the composed transcript
    "tell me about jazz"      -> the honest fallback (no keys, no model)

Run: python examples/demo_provider.py
"""

from nexusagent import Agent, DemoProvider, InMemoryMemory, ToolExecutor
from nexusagent.tool_factory import create_tool_registry


def main() -> None:
    provider = DemoProvider()
    agent = Agent(
        provider,
        tool_registry=create_tool_registry(),
        tool_executor=ToolExecutor(),
        memory=InMemoryMemory(),
    )

    for prompt in (
        "what color is the sky?",
        "who start first in chess? black or white",
        "what is 144 / 12?",
        "my name is Sara",
        "what is my name?",
        "tell me about jazz",
    ):
        result = agent.run(prompt)
        print(f"you: {prompt}")
        print(f"  -> {result.output}  (provider call #{provider.calls})")
        print()

    print("streaming the same sky answer word by word:")
    chunks: list[str] = []
    agent.run("what color is the sky?", on_delta=chunks.append)
    print("  " + "".join(chunks).strip())


if __name__ == "__main__":
    main()
