# Guide: Writing a Custom Provider

A `Provider` is the model backend. You only need to implement one method to
plug yours in — and if it can only answer with text, you don't even need
that.

## Text-only provider: implement `generate()`

```python
from nexusagent.provider import Provider, ProviderConfig


class EchoModel(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        return f"you said: {prompt}"
```

The base class's default `generate_response()` wraps your `generate()`, so
this provider already works with `Agent.run()`, `Runtime.run()`, and the
CLI — it will simply never request tools.

## Tool-aware provider: override `generate_response()`

To let the model request tools, return a `ToolCallRequest` (or a
`TextResponse`) from `generate_response`:

```python
from collections.abc import Sequence

from nexusagent.provider import (
    Provider,
    ProviderResponse,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)


class ToolLoverProvider(Provider):
    """Always requests the first advertised tool, then answers with text."""

    def generate(self, prompt: str) -> str:
        return "done"

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> ProviderResponse:
        if not tool_results and tools:
            return ToolCallRequest(tool_name=tools[0].name, tool_input=prompt)
        return TextResponse("all tool results are in: " + str(tool_results))
```

The contract:

- `tools` — what the agent can run. Empty when the agent has no tools.
- `tool_results` — outcomes of the tool calls **you** requested earlier in
  this run, oldest first. `ToolResult.is_error == True` means the call
  failed; the `output` then holds the error message. Recovery is your job:
  retry with different input, try another tool, or explain in text.
- The agent stops asking after `max_iterations` (default 10) provider calls,
  so a provider that never returns `TextResponse` ends the run with a failed
  `AgentResult` — it cannot loop forever.

## Provider errors

Raise the typed exceptions from `nexusagent.provider` so callers get clean,
distinguishable failures:

| Exception | Use for |
| --- | --- |
| `ProviderConfigurationError` | bad/missing config, detected before any I/O |
| `ProviderRequestError` | the request failed (network, status, timeout) |
| `ProviderResponseError` | the backend answered with something unusable |

`Agent.run()` turns any provider exception into a failed
`AgentResult(output="provider error: ...")` — it never propagates into
caller code.

## For real backends

`HttpProvider` already speaks a small vendor-neutral HTTP protocol — put an
adapter in front of OpenAI, Anthropic, or a local model server and you have
a provider with zero code changes to the core. See
[protocol.md](../protocol.md), and
[`examples/http_provider_local.py`](../../examples/http_provider_local.py)
for a working local backend. Vendor adapters are tracked as future work in
[ADR 0002](../adr/0002-tool-call-wire-format-and-agent-loop.md).

## Testing your provider

`ScriptedProvider` (in `nexusagent.providers`) shows the shape of a
deterministic, testable provider and is directly usable in your own tests:
script `ToolCallRequest`s and `TextResponse`s and assert on what the loop
did. See `tests/test_tool_loop.py` for the pattern.
