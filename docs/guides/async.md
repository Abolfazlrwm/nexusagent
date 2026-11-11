# Guide: Async Execution

Everything in the sync core works unchanged; the async layer (ADR 0006) adds
awaited mirrors of the same contracts. Same response protocol, same bounded
tool loop, same error semantics — you just `await`.

## 1. Run the async runtime

```python
import asyncio

from nexusagent import create_async_runtime


async def main() -> None:
    runtime = create_async_runtime()  # offline `fake` provider by default
    result = await runtime.run("Hello NexusAgent")
    print(result.output)  # fake response: Hello NexusAgent

    print(await runtime.execute_tool("calculator", "2 + 3"))  # 5


asyncio.run(main())
```

`create_async_runtime()` takes the same `NEXUS_*` settings as the sync
runtime — including `NEXUS_PROVIDER=openai`. Any sync provider the factory
returns is bridged automatically.

## 2. How sync providers work under the loop

`SyncProviderAdapter` wraps any sync `Provider` and runs its blocking calls
in worker threads (`asyncio.to_thread`), so the event loop never stalls:

```python
from nexusagent import AsyncAgent
from nexusagent.async_provider import SyncProviderAdapter
from nexusagent.providers import FakeProvider

agent = AsyncAgent(SyncProviderAdapter(FakeProvider()))
result = await agent.run("hi")
```

No HTTP client library is bundled — the adapter is the bridge, and a
natively async backend would subclass `AsyncProvider` instead.

## 3. Write an async tool

```python
from nexusagent.async_tool_executor import AsyncToolExecutor
from nexusagent.tool import AsyncTool
from nexusagent.tool_registry import ToolRegistry


class FetchTool(AsyncTool):
    def __init__(self) -> None:
        super().__init__(
            name="fetch",
            description="Fetches a document. Describe it for the model.",
        )

    async def aexecute(self, input_data: str) -> str:
        # real awaited I/O goes here (httpx, aiohttp, databases, ...)
        return f"document about {input_data}"


registry = ToolRegistry()
registry.register(FetchTool())
executor = AsyncToolExecutor()
```

Rules:

- An `AsyncTool` **cannot** run on the sync path — its `execute()` fails
  fast with a clear `NotImplementedError` instead of leaking a coroutine.
- Plain sync tools keep working under `AsyncToolExecutor` (run in a worker
  thread), so you can mix both kinds in one registry.
- Validation and `ToolExecutionError` wrapping are identical to the sync
  executor.

## 4. Concurrency

Multiple runs interleave in one event loop:

```python
import asyncio

results = await asyncio.gather(agent_a.run("first"), agent_b.run("second"))
```

Each `run()` keeps its own tool results; providers are stateless by
contract (ADR 0002), so nothing is shared behind your back.

## Testing your own async code

`pytest-asyncio` ships with the `dev` extra (strict mode is configured in
`pyproject.toml`); mark your tests with `@pytest.mark.asyncio`. It is a
**dev-only** dependency — installing `nexusagent-runtime` at runtime still
pulls zero packages.

Run the offline demo:

```bash
python examples/async_tool_loop.py
```
