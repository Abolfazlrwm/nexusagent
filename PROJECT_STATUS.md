# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE

- 623 tests, all passing (includes an end-to-end test against a real local HTTP server).
- `ruff check .` — clean.
- `ruff format --check .` — clean.
- `python scripts/check.py` — passes (also runs in CI, Python 3.10 – 3.13).
- No known bugs, no known regressions, no unfinished/half-done code.

This is a safe point to stop at. Nothing is broken or left mid-change.

## What NexusAgent can actually do today

A real, working, tested agent runtime with an **autonomous tool loop**:

- Run a prompt through a Provider (`FakeProvider` for offline/dev use,
  `HttpProvider` for a real HTTP backend, `ScriptedProvider` for demos/tests)
  via `Agent.run()` / `Runtime.run()`.
- If the Provider answers with a tool-call request, the Agent runs that tool
  itself, feeds the result back, and asks again — until the Provider answers
  in plain text or `max_iterations` (default 10) is reached.
- Tool failures (unknown tool, invalid input, crash) do not abort the run;
  they are fed back to the Provider as error results so it can recover.
- Register and run explicit, named tools (`EchoTool`, `UppercaseTool`,
  `CalculatorTool`) through `Agent.execute_tool()` / `Runtime.execute_tool()`,
  from Python or the CLI (`python -m nexusagent tool run ...`).
- Configure everything through `Settings` (env vars prefixed `NEXUS_`,
  or explicit construction).

## Decision made: the tool-call wire format

The blocker from the previous snapshot is resolved. NexusAgent defines its own
minimal, vendor-neutral format (option 1 of the old resume point). Full spec:
[`docs/protocol.md`](docs/protocol.md).

- Response is exactly one of `{"output": "..."}` or
  `{"tool_name": "...", "tool_input": "..."}`.
- Request gains optional `tools` (what the agent can run) and `tool_results`
  (results so far), and is byte-for-byte unchanged when neither applies.

Backward compatibility: `Provider.generate() -> str` is unchanged. A new
non-abstract `Provider.generate_response()` returns a `ProviderResponse`;
its default wraps `generate()`, so text-only providers need no changes. The
Agent also still accepts duck-typed providers that only define `generate()`.
`AgentResult` is unchanged (`output`, `success`).

## What does NOT exist yet

- Adapters for specific vendor APIs (OpenAI, Anthropic, ...). Write one as a
  small service speaking `docs/protocol.md`, or as a new `Provider` subclass
  that overrides `generate_response()`.
- Tool inputs are still a single string. Structured/JSON tool arguments and
  tool schemas would be the next protocol revision.
- Conversation memory / multi-turn history, planning, streaming, async.
- Loop configuration through `Settings` / the CLI (`max_iterations` is only an
  `Agent(...)` constructor argument today — adding a `NEXUS_MAX_ITERATIONS`
  setting also means updating the exact-`repr` tests in `tests/test_config.py`).
- `AgentResult` does not expose a trace of tool calls (they are logged at
  INFO/DEBUG under `nexusagent.agent`). Adding a field means updating
  `test_agent_result_has_exactly_output_and_success_fields`.

## Suggested next steps

1. Pick one real backend and write its adapter (see above).
2. Decide on structured tool arguments; bump the protocol doc when you do.
3. Then consider surfacing a tool-call trace on `AgentResult`.

## One intentional change to an old test

`tests/test_agent.py::ExplodingRegistry` gained a `list_tools()` method,
because the Agent now lists tools to advertise them to the Provider. The
original intent still holds and is still tested: a plain text answer never
looks up or executes a tool.

## How to run things

```bash
pip install -e ".[dev]"
python -m pytest              # run the test suite
ruff check .                  # lint
ruff format --check .         # format check
python scripts/check.py       # full project check (used in CI-style validation)

python -m nexusagent "your prompt here"          # run the agent
python -m nexusagent tool list                   # list built-in tools
python -m nexusagent tool run echo "hello"        # run a tool directly
python examples/tool_loop_demo.py                # watch the tool loop, offline
```
