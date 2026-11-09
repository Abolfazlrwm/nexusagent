"""Define a custom tool and run it through an application runtime.

Run from the repository root:

    python examples/custom_tool.py

No configuration, API key, or network access is required.
"""

from nexusagent import Settings, create_runtime
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class WordCountTool(Tool):
    """Counts words and characters in the given text."""

    def __init__(self) -> None:
        super().__init__(
            name="wordcount",
            description="Counts words and characters in the input text.",
        )

    def execute(self, input_data: str) -> str:
        words = len(input_data.split())
        chars = len(input_data)
        return f"{words} words, {chars} characters"


def main() -> None:
    settings = Settings(provider="fake")

    registry = ToolRegistry()
    registry.register(WordCountTool())

    runtime = create_runtime(settings, tool_registry=registry, tool_executor=ToolExecutor())

    result = runtime.execute_tool("wordcount", "NexusAgent makes agent runtimes readable")
    print("wordcount:", result)


if __name__ == "__main__":
    main()
