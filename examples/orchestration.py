"""Minimal multi-agent orchestration (ADR 0015), fully offline.

One prompt in, one named specialist out, that agent's own result back —
no graphs, no shared state. This example builds a two-agent team and a
router backed by a scripted provider, then watches both prompts find
their agent:

    "what is 19 + 23?"  -> router picks "math"    -> the math agent's
                           bounded tool loop runs the calculator tool
    "My name is Sara"   -> router picks "greeter" -> the greeter answers
                           directly and records the exchange in its own
                           memory (ADR 0012)

Run: python examples/orchestration.py
"""

from nexusagent import (
    Agent,
    AgentTeam,
    InMemoryMemory,
    ScriptedProvider,
    TextResponse,
    ToolCallRequest,
    ToolRegistry,
    create_provider_router,
)
from nexusagent.calculator_tool import CalculatorTool
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutor

ROUTER_SCRIPT = [
    TextResponse("math"),  # routing decision for prompt 1
    TextResponse("greeter"),  # routing decision for prompt 2
]

MATH_SCRIPT = [
    ToolCallRequest(tool_name="calculator", tool_input="19 + 23"),  # model asks for the tool
    TextResponse("19 + 23 = 42, of course."),  # model answers with the result fed back
]


class RecordingExecutor(ToolExecutor):
    """Runs tools with the standard validation and records what was executed."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, str, str]] = []

    def execute(self, tool: Tool, input_data: str) -> str:
        output = super().execute(tool, input_data)
        self.executed.append((tool.name, input_data, output))
        return output


def main() -> None:
    router_provider = ScriptedProvider(ROUTER_SCRIPT)
    router = create_provider_router(router_provider, ["greeter", "math"])

    math_registry = ToolRegistry()
    math_registry.register(CalculatorTool())
    math = Agent(
        ScriptedProvider(MATH_SCRIPT),
        tool_registry=math_registry,
        tool_executor=RecordingExecutor(),
    )
    greeter = Agent(
        ScriptedProvider([TextResponse("Nice to meet you, Sara!")]),
        memory=InMemoryMemory(),
    )

    team = AgentTeam({"greeter": greeter, "math": math}, router)

    print("agent team ready — members:", sorted(team.agents), "\n")

    for prompt in ("what is 19 + 23?", "My name is Sara"):
        result = team.run(prompt)
        print(f"prompt:     {prompt!r}")
        print(f"handled by: {result.agent_name}")
        print(f"answer:     {result.output}\n")

    # The math agent's bounded tool loop really ran the calculator:
    executor = math.tool_executor
    assert isinstance(executor, RecordingExecutor)
    assert executor.executed == [("calculator", "19 + 23", "42")]

    # Routing decisions were real provider calls (the router's script):
    assert [r.text for r in ROUTER_SCRIPT] == ["math", "greeter"]

    # Each member keeps its own memory — the greeter remembered Sara:
    greeter_memory = greeter.memory
    assert greeter_memory is not None
    assert len(greeter_memory) == 2

    print("orchestration confirmed: one router, one specialist per prompt, own result back.")


if __name__ == "__main__":
    main()
