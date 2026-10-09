"""Write your own tool and give it to an agent.

Run with a real model, e.g. a local Ollama server (no API key needed):

    NEXUS_PROVIDER=openai NEXUS_MODEL=llama3.1 \
    NEXUS_ENDPOINT=http://localhost:11434/v1/chat/completions \
    python examples/custom_tool.py
"""

from nexusagent import Settings
from nexusagent.agent import Agent
from nexusagent.factory import create_provider
from nexusagent.provider import ProviderConfig
from nexusagent.tool import Tool
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry


class WordCountTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="word_count", description="Counts the words in the given text.")

    def execute(self, input_data: str) -> str:
        return str(len(input_data.split()))


settings = Settings.from_env()
settings.validate()

registry = ToolRegistry()
registry.register(WordCountTool())

provider = create_provider(
    settings.provider,
    ProviderConfig(
        model=settings.model,
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        timeout=settings.timeout,
    ),
)
agent = Agent(provider, tool_registry=registry, tool_executor=ToolExecutor())

result = agent.run("How many words are in: 'the quick brown fox jumps'?")
print(result.output)
