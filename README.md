# NexusAgent

NexusAgent is a modular AI agent runtime. Rather than being a chatbot or a thin wrapper around a single LLM API, it provides the surrounding system an agent needs: a stable execution core (`Agent`), a pluggable model backend (`Provider`), a small set of callable capabilities (`Tools`), and an application layer that wires these together into a `Runtime`.

The project is under active, incremental development. The current implementation is deliberately small: a synchronous `Agent` around a `Provider` with an **autonomous tool loop** — the model can ask for a tool, the agent runs it, feeds the result back, and repeats until the model answers (bounded by an iteration limit). Tools can also still be invoked explicitly. There is currently no planning or memory.

## Architecture

```text
Provider   — generates a response for a given input (e.g. FakeProvider, HttpProvider)
Agent      — validates input, runs the Provider <-> Tool loop, and can execute an explicitly named Tool
Tools      — small, independent callables (echo, uppercase, calculator) invoked by name,
             either explicitly or because the Provider requested them
Runtime    — wires a configured Agent (and, if provided, the Tool subsystem) together
Factories  — construct Providers/Tools/Runtime from Settings (tool_factory, runtime_factory,
             application layer) so callers don't need to assemble these pieces by hand
```

`Runtime.run(...)` drives the Provider path, including the tool loop; `Runtime.execute_tool(...)` explicitly invokes one named Tool. The Agent never *chooses* a tool itself — the Provider does, by returning a tool-call request — and the Agent only ever runs tools that are registered.

## The tool loop

```text
prompt ──▶ Provider ──▶ text answer ─────────────────────▶ done
              ▲  └────▶ tool-call request ──▶ run tool ──┐
              └────────────── tool result ◀──────────────┘   (max 10 rounds)
```

- A tool failure (unknown tool, bad input, crash) is **not** fatal: it is sent back to the Provider as an error result so it can retry or explain.
- Runaway providers are stopped by `Agent(max_iterations=...)` (default 10); hitting the limit returns `success=False`.
- Providers that only return text (like `fake`) keep working unchanged.

See it live, offline, with no API key:

```bash
python examples/tool_loop_demo.py
```

## Public API

The supported way to use NexusAgent as a library is through the package root:

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

- `create_application_runtime(settings=None)` — the recommended entry point; returns a fully configured `Runtime` with the built-in Tools (`echo`, `uppercase`, `calculator`) registered.
- `create_runtime(settings=None, tool_registry=None, tool_executor=None)` — a lower-level constructor for a `Runtime`; Tools are only attached if you supply a `tool_registry`/`tool_executor` yourself.
- `Runtime` — holds a configured `Agent` and exposes `run(...)`, `execute_tool(...)`, and `list_tools()`.
- `Agent` — validates input, runs the Provider/Tool loop, and (optionally) executes a named Tool. Takes `max_iterations` (default 10).
- `AgentResult` — the immutable `(output: str, success: bool)` result of `Agent.run(...)`.
- `Settings` — configuration (provider selection, model, API key, endpoint, timeout), normally built via `Settings.from_env()`.

Everything else (`Tool`, `ToolRegistry`, `ToolExecutor`, `Provider`, `FakeProvider`, `HttpProvider`, the built-in `EchoTool`/`UppercaseTool`/`CalculatorTool`, and the various factory modules) is internal implementation detail. It exists under `nexusagent.*` submodules and may change without notice — only the symbols listed above are the intended public API.

## Basic usage

```python
from nexusagent import create_application_runtime

runtime = create_application_runtime()

result = runtime.run("Hello NexusAgent")
print(result.output)  # fake response: Hello NexusAgent
print(result.success)  # True

print(runtime.execute_tool("calculator", "2 + 3"))  # 5
```

By default `create_application_runtime()` uses the deterministic, network-free `fake` provider, so this example runs with no configuration. To use the generic HTTP provider instead, pass `Settings(provider="http", endpoint=...)` — see the [Providers](#providers) section below.

## Installation

NexusAgent is not currently published on PyPI. For local development, clone the repository and install it in editable mode:

```bash
git clone https://github.com/Abolfazlrwm/nexusagent
cd nexusagent
pip install -e ".[dev]"
```

This installs the `nexusagent` package along with its development dependencies (`pytest`, `ruff`).

## Providers

NexusAgent selects a provider via `NEXUS_PROVIDER` (or `--provider` on the CLI). Two providers exist today:

- `fake` (default) — deterministic, no network access.
- `http` — a generic HTTP provider. It sends `{"model": ..., "input": ...}` as a JSON POST to a configured endpoint (plus `tools` and `tool_results` when the agent has tools) and expects a JSON response that is either `{"output": "..."}` (final answer) or `{"tool_name": "...", "tool_input": "..."}` (please run this tool). It is not tied to any specific vendor. The full wire format is documented in [docs/protocol.md](docs/protocol.md).

Relevant environment variables:

- `NEXUS_PROVIDER` — provider name (`fake` or `http`)
- `NEXUS_MODEL` — model identifier passed to the provider
- `NEXUS_API_KEY` — sent as a `Bearer` token if set
- `NEXUS_ENDPOINT` — HTTP provider endpoint URL
- `NEXUS_TIMEOUT` — HTTP request timeout in seconds (default `30`)

The `http` provider only performs a network request when it actually runs — selecting it does not make any request on its own.

## Tools

Available tools can be listed from the CLI:

```bash
python -m nexusagent tool list
```

```text
echo - Returns its input unchanged.
uppercase - Converts input to uppercase.
calculator - Performs basic arithmetic operations.
```

A registered tool can be run directly from the CLI:

```bash
python -m nexusagent tool run echo "hello world"
```

```text
hello world
```

```bash
python -m nexusagent tool run uppercase "hello world"
```

```text
HELLO WORLD
```

```bash
python -m nexusagent tool run calculator "2 + 3"
```

```text
5
```

Currently the built-in `echo`, `uppercase`, and `calculator` tools are available.

## Development

NexusAgent is being developed incrementally, through small, focused changes.

Run all local quality checks (lint, format check, tests) with:

```bash
python scripts/check.py
```

The same checks run in CI on every push and pull request (Python 3.10 – 3.13).
Architecture rules (which module may import which) are enforced by `tests/test_architecture.py`.
