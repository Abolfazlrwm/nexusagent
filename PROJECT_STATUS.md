# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE

- 578 tests, all passing.
- `ruff check .` — clean.
- `ruff format --check .` — clean.
- `python scripts/check.py` — passes.
- No known bugs, no known regressions, no unfinished/half-done code.

This is a safe point to stop at. Nothing is broken or left mid-change.

## What NexusAgent can actually do today

A real, working, tested agent runtime that can:

- Run a prompt through a Provider (`FakeProvider` for offline/dev use,
  `HttpProvider` for a real HTTP backend) and get back a plain text
  answer via `Agent.run()` / `Runtime.run()`.
- Register and run explicit, named tools (`EchoTool`, `UppercaseTool`,
  `CalculatorTool`) through `Agent.execute_tool()` / `Runtime.execute_tool()`,
  either from Python or from the CLI (`python -m nexusagent tool run ...`).
- Check whether a tool is available without executing it
  (`Agent.has_tool()` / `ToolRegistry.has()`).
- Configure everything through `Settings` (env vars prefixed `NEXUS_`,
  or explicit construction).

None of this is a toy — every layer (Provider, Tool, Registry, Executor,
Agent, Runtime, and all four factories) has been independently and
thoroughly contract-tested, with explicit architecture rules preventing
lower layers from depending upward on higher ones.

## What does NOT exist yet (this is the important part)

**There is no autonomous agent loop.** Tool execution is 100% manual —
a human (or calling code) has to explicitly say "run this tool with
this input." The model/provider cannot request a tool call and have it
executed automatically, get the result fed back, and continue reasoning.

Concretely, `Provider.generate()` still only returns a plain `str`.
Structured response types (`TextResponse`, `ToolCallRequest`,
`ProviderResponse`) exist in `src/nexusagent/provider.py` but are
**not produced by any Provider and not consumed by Agent.run()**. They
are prepared groundwork, not active behavior.

## Why it stopped here (not a bug — a deliberate blocker)

Building the actual loop requires a real answer to one question first:

> **What wire format will a real backend use to say "call this tool
> with this input" instead of "here is a text answer"?**

Nothing in the codebase currently defines this. `HttpProvider` only
recognizes `{"output": "..."}`. Inventing a made-up format now would
mean building a parser for a protocol that might not match whatever
backend actually gets used later — pure wasted, throwaway work.

**This is the single decision that unblocks everything else.**

## Exact resume point — read this first when you come back

1. Decide the tool-call response shape. Two real options:
   - Design NexusAgent's own minimal format (e.g. HTTP response body
     can contain either `{"output": "..."}` or
     `{"tool_name": "...", "tool_input": "..."}`), and update
     `HttpProvider` to recognize both and produce a `ToolCallRequest`
     for the second case.
   - Or, if you already know which real LLM API you'll actually call
     (OpenAI, Anthropic, etc.), base the shape on that API's real
     tool-call response format instead of inventing one.
2. Once `HttpProvider` (or a new Provider) can genuinely produce a
   `ToolCallRequest`, revisit whether `Agent.run()` should consume
   `ProviderResponse` instead of a plain `str`, and design the
   smallest clean loop: provider responds → if it's a tool call,
   execute it via the existing `Agent.execute_tool()` → feed the
   result back to the provider → provider responds again → repeat
   until it's a plain text answer (with a hard iteration limit).
3. Only after that loop exists and is tested does it make sense to
   revisit whether `AgentResult` needs to change, whether the CLI
   needs new flags, etc.

Do not start by building loop machinery in the abstract — start by
picking the real response shape in step 1. Everything else follows
from that.

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
```
