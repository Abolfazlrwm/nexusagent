# Concepts

The five nouns of NexusAgent and how they fit together.

## Provider

A `Provider` is the model backend: it receives the conversation state and
produces either text or a tool request.

```python
class Provider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse: ...
```

- `generate()` is the minimal contract — a text answer.
- `generate_response()` is optional to override and may return a
  `TextResponse` or a `ToolCallRequest`. The default implementation wraps
  `generate()`, so **text-only providers need no changes**.
- Built-ins: `FakeProvider` (echoes, offline), `ScriptedProvider` (replays a
  fixed script — great for demos/tests), `HttpProvider` (speaks
  [the wire protocol](protocol.md)).

## Tool

A `Tool` is a small, named capability the agent can execute:

```python
class Tool(ABC):
    def __init__(self, name: str, description: str) -> None: ...
    @abstractmethod
    def execute(self, input_data: str) -> str: ...
```

Tools take and return plain strings — deliberately primitive, so any model
backend can call them without an argument-marshalling schema. Validation
errors (bad types, empty names) are raised at construction/registration
time, not deep inside a run.

## ToolRegistry & ToolExecutor

- `ToolRegistry` maps names to tools; duplicate registration and unknown
  lookups are explicit errors.
- `ToolExecutor` runs a tool and wraps any failure in `ToolExecutionError`
  (the original error class is preserved in the message, and as `__cause__`).

Together they are the **extension point** for custom tools — see
[the guide](guides/custom-tool.md).

## Agent

The `Agent` owns the run loop:

1. Validate input (must be a non-empty string).
2. Ask the provider for a response, advertising available tools.
3. If the provider requests a tool: run it, collect a `ToolResult`, repeat —
   bounded by `max_iterations` (default 10).
4. Otherwise return an `AgentResult(output, success)`.

`Agent` never calls tools the provider did not ask for, never runs more
iterations than allowed, and never crashes the run on a provider or tool
error — it returns a failed `AgentResult` (or a `ToolResult(is_error=True)`
that the provider can recover from).

## Runtime

The `Runtime` is the facade most code should hold: `run()`, `execute_tool()`,
`list_tools()`. Construct it via:

- `create_application_runtime(settings=None)` — full setup with the three
  built-in tools; the recommended entry point.
- `create_runtime(settings, tool_registry=None, tool_executor=None)` —
  lower-level; tools are attached only if you pass a registry/executor.

## Async execution

The async layer (ADR 0006) mirrors every sync contract — nothing is
re-invented, everything is awaited:

- `AsyncAgent` / `AsyncRuntime` / `create_async_runtime()`: the same bounded
  tool loop with the same `AgentResult` and error semantics, run from a
  live event loop.
- `SyncProviderAdapter`: wraps any sync provider (including `openai`,
  `anthropic` and `http`) so it drives `AsyncAgent`; blocking calls run in worker threads
  via `asyncio.to_thread`, so the loop never stalls.
- `AsyncTool` + `AsyncToolExecutor`: awaited tools; plain sync tools keep
  working alongside them in the same registry.

Importing `nexusagent` never starts an event loop; concurrency happens only
inside code you write (`asyncio.run`, web-framework handlers, ...). See the
[async guide](guides/async.md).

## Settings

`Settings` is a frozen dataclass built from `NEXUS_*` environment variables
(`Settings.from_env()`) or constructed directly. `validate()` checks the
combination locally — wrong combinations fail fast, before any network call.
`api_key` never appears in logs or reprs.

## Error taxonomy

| Exception | Raised when |
| --- | --- |
| `ProviderConfigurationError` | endpoint missing, bad timeout, unknown provider name |
| `ProviderRequestError` | the HTTP call itself failed (status, connection, timeout) |
| `ProviderResponseError` | the response was not valid protocol JSON |
| `ToolExecutionError` | a tool's `execute()` raised |
| `ValueError` / `TypeError` | invalid settings/inputs, validated early |
