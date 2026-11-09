# Guide: Writing a Custom Tool

Tools are how an agent acts. A NexusAgent tool is a small class with a name,
a description, and a string→string function.

## 1. Subclass `Tool`

```python
from nexusagent.tool import Tool


class WordCountTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="wordcount",
            description="Counts words and characters in the input text.",
        )

    def execute(self, input_data: str) -> str:
        return f"{len(input_data.split())} words"
```

Rules the base class enforces:

- `name` and `description` must be non-empty strings — they are what the
  provider sees when deciding whether to request the tool, so write the
  description for the *model*, not for humans.
- Names must be unique in a registry.

## 2. Register it

```python
from nexusagent import Settings, create_runtime
from nexusagent.tool_executor import ToolExecutor
from nexusagent.tool_registry import ToolRegistry

registry = ToolRegistry()
registry.register(WordCountTool())

runtime = create_runtime(
    Settings(provider="fake"),
    tool_registry=registry,
    tool_executor=ToolExecutor(),
)
```

`create_runtime` attaches tools only when you pass a registry/executor;
`create_application_runtime()` always builds the three built-ins
(`echo`, `uppercase`, `calculator`).

## 3. Run it

```python
print(runtime.execute_tool("wordcount", "one two three"))  # explicit
result = runtime.run("How many words are in this sentence?")
# if the provider knows how to request tools, it may call it autonomously
```

## Error handling

Raise any exception inside `execute()` — the executor wraps it in
`ToolExecutionError` (the original class stays in the message and as
`__cause__`). Inside the autonomous loop, a failed tool call becomes an
error `ToolResult` that the provider sees, so it can retry with different
input instead of crashing the run:

```python
class SafeDivTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="safediv", description="Divides a by b. Pass 'a b'.")

    def execute(self, input_data: str) -> str:
        a, b = (float(x) for x in input_data.split())
        if b == 0:
            raise ValueError("b must not be zero")  # model sees this message
        return str(a / b)
```

## Testing your tool

Mirror the built-ins' style: construction contract (bad name/description
rejected), execution contract, and error wrapping. See
`tests/test_echo_tool.py` for the pattern.

A complete runnable version lives in
[`examples/custom_tool.py`](../../examples/custom_tool.py).
