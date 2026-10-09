"""The agent loop, end to end, with no network and no API key.

A ScriptedProvider plays the part of a model: first it asks for the calculator
tool, then it answers using the tool's result.
"""

from nexusagent.agent import Agent
from nexusagent.provider import ToolCallRequest
from nexusagent.providers import ScriptedProvider
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_factory import create_tool_registry

model = ScriptedProvider([ToolCallRequest("calculator", "1234 * 5"), "1234 times 5 is 6170."])
agent = Agent(model, tool_registry=create_tool_registry(), tool_executor=ToolExecutor())

result = agent.run("What is 1234 * 5?")

for step in result.steps:
    print(f"tool {step.tool_name}({step.tool_input!r}) -> {step.tool_output}")
print(result.output)
