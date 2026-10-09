# NexusAgent

[![CI](https://github.com/Abolfazlrwm/nexusagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Abolfazlrwm/nexusagent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A small, readable runtime for AI agents in Python. **No third-party dependencies** — standard library only.

NexusAgent gives a model what it needs to act: a pluggable **provider** (OpenAI-compatible APIs, Anthropic, or your own HTTP backend), a set of **tools** it can call, and an **agent loop** that runs a requested tool, feeds the result back, and repeats until the model gives a final answer.

```text
you ──► Agent ──► Provider (LLM) ──► "call tool X"
          ▲                              │
          └──── tool result ◄── ToolExecutor ◄┘      …until a final text answer
```

## Install

Not yet on PyPI. From a clone:

```bash
git clone https://github.com/Abolfazlrwm/nexusagent
cd nexusagent
pip install -e ".[dev]"
```

## Quick start (offline, no API key)

```python
from nexusagent import create_application_runtime

runtime = create_application_runtime()  # fake provider by default
print(runtime.run("Hello NexusAgent").output)  # fake response: Hello NexusAgent
print(runtime.execute_tool("calculator", "2 + 3"))  # 5
```

See the tool loop run without any network — [`examples/tool_loop_offline.py`](examples/tool_loop_offline.py):

```python
model = ScriptedProvider([ToolCallRequest("calculator", "1234 * 5"), "1234 times 5 is 6170."])
agent = Agent(model, tool_registry=create_tool_registry(), tool_executor=ToolExecutor())
result = agent.run("What is 1234 * 5?")
# result.steps  -> (AgentStep(tool_name='calculator', tool_input='1234 * 5', tool_output='6170'),)
# result.output -> '1234 times 5 is 6170.'
```

## Use a real model

Configuration is read from environment variables (or pass a `Settings(...)`).

| Variable | Meaning | Default |
| --- | --- | --- |
| `NEXUS_PROVIDER` | `fake`, `http`, `openai`, `anthropic` | `fake` |
| `NEXUS_MODEL` | model identifier (required for `openai` / `anthropic`) | – |
| `NEXUS_API_KEY` | API key (required for `anthropic`; optional for local servers) | – |
| `NEXUS_ENDPOINT` | endpoint URL (required for `http`; optional override for the others) | provider default |
| `NEXUS_TIMEOUT` | request timeout, seconds | `30` |
| `NEXUS_SYSTEM_PROMPT` | system prompt for the agent | – |
| `NEXUS_MAX_STEPS` | max model/tool round-trips per run (1–100) | `8` |
| `NEXUS_LOG_LEVEL` | `DEBUG`, `INFO`, … | `INFO` |

**Local model with Ollama** (free, private, no key):

```bash
export NEXUS_PROVIDER=openai NEXUS_MODEL=llama3.1
export NEXUS_ENDPOINT=http://localhost:11434/v1/chat/completions
python -m nexusagent "What is 1234 * 5? Use the calculator." -v
```

**OpenAI** (or any OpenAI-compatible service such as OpenRouter, Groq, LM Studio, vLLM):

```bash
export NEXUS_PROVIDER=openai NEXUS_MODEL=<model-id> NEXUS_API_KEY=sk-...
python -m nexusagent "Uppercase the word hello"
```

**Anthropic:**

```bash
export NEXUS_PROVIDER=anthropic NEXUS_MODEL=<model-id> NEXUS_API_KEY=...
python -m nexusagent "What is 2 + 3?"
```

(Check your provider's docs for current model IDs.)

## Command line

```bash
python -m nexusagent "your prompt"          # one-shot run
python -m nexusagent chat                   # interactive, remembers the conversation
python -m nexusagent tool list              # list built-in tools
python -m nexusagent tool run echo "hello"  # run a tool directly
```

Options for runs and `chat`: `--provider`, `--model`, `--max-steps`, `--system`, `-v/--verbose` (logs every tool call to stderr). In `chat`, `/reset` clears the history and `/exit` (or Ctrl-D) quits.

## Library API

```python
from nexusagent import (
    Agent,
    AgentResult,
    Runtime,
    Settings,
    create_application_runtime,
    create_runtime,
)
```

- `create_application_runtime(settings=None)` — recommended entry point; a `Runtime` with the built-in tools registered.
- `Runtime.run(text)` → `AgentResult(output, success, steps, messages)`; `Runtime.conversation()` → a multi-turn `Conversation` (`.send(text)`, `.reset()`).
- `AgentResult.steps` lists each tool call made (`tool_name`, `tool_input`, `tool_output`, `is_error`).

Everything else (`Tool`, `ToolRegistry`, providers, factories, …) lives under `nexusagent.*` submodules and may change; see the examples for how to use them directly.

### How the loop behaves

- The provider is told which tools exist; if it answers with a tool call, the agent runs it and sends the result back.
- **Tool errors don't crash the run.** An unknown tool, bad input, or a tool raising is reported to the model as `error: …` so it can correct itself.
- A run that doesn't finish within `max_steps` returns `success=False` instead of looping forever.
- Provider failures return `success=False` with a `provider error: …` message; API keys never appear in errors or `repr`s.

### Writing a tool

```python
from nexusagent.tool import Tool


class WordCountTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="word_count", description="Counts the words in the given text.")

    def execute(self, input_data: str) -> str:
        return str(len(input_data.split()))
```

Tools take and return a single string. To models they appear as a function with one string parameter, `input`. Full example: [`examples/custom_tool.py`](examples/custom_tool.py).

## Generic HTTP provider wire format

`NEXUS_PROVIDER=http` talks to any backend you control. The agent loop POSTs:

```json
{"model": "...", "input": "<last user text>",
 "messages": [{"role": "user", "content": "..."}],
 "tools": [{"name": "calculator", "description": "..."}]}
```

and accepts either a final answer or a tool call:

```json
{"output": "final text"}
{"tool_name": "calculator", "tool_input": "2 + 3", "call_id": "optional"}
```

Messages for tool turns carry `tool_name`, `tool_input` and `call_id` next to `role`/`content`.

## Architecture

```text
Provider   — turns a conversation into a response (Fake, Scripted, Http, OpenAI, Anthropic)
Agent      — the loop: ask provider → run requested tool → feed result back → repeat
Tools      — small string-in/string-out callables (echo, uppercase, calculator)
Runtime    — a configured Agent (+ tool subsystem)
Factories  — build providers / tools / runtime from Settings
```

Layering rules (e.g. "`agent` never imports a concrete provider", "no third-party dependencies") are enforced by tests in `tests/test_architecture.py`.

## Development

```bash
python scripts/check.py   # ruff check, ruff format --check, mypy (strict), pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md) and [PROJECT_STATUS.md](PROJECT_STATUS.md).

## License

MIT
