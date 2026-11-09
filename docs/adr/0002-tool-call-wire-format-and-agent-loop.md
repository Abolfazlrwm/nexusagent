# ADR 0002: Tool-Call Wire Format and the Autonomous Agent Loop

- Status: Accepted
- Date: 2026-10-01 (implemented), 2026-11-09 (recorded)
- Deciders: Abolfazl Ranjbaran

## Context

Until 0.3.0, `Provider.generate()` returned a plain `str` and tool execution
was 100% manual: a caller had to explicitly name and run every tool. The
project's own status document identified this as the central blocker:

> What wire format will a real backend use to say "call this tool with this
> input" instead of "here is a text answer"?

Two options were considered:

1. **Base the format on a specific vendor API** (e.g. OpenAI's or Anthropic's
   tool-call JSON). This couples the generic `HttpProvider` to one vendor's
   evolving schema and makes the "vendor-neutral, stdlib-only core" claim
   dishonest.
2. **Define NexusAgent's own minimal JSON shape** for structured responses,
   and keep vendor adaptation as a separate concern (a thin Provider that
   translates a vendor API into the NexusAgent shape).

## Decision

Option 2. `Provider` gains an optional structured contract:

- `Provider.generate_response(prompt, *, tools, tool_results) -> ProviderResponse`
  where `ProviderResponse = TextResponse | ToolCallRequest` (default
  implementation wraps `generate()` and only answers with text, so
  text-only providers need no changes).
- `ToolSpec(name, description)` advertises available tools; `ToolResult`
  carries a tool call's outcome (with `is_error`) back to the provider.
- The HTTP wire format (see `docs/protocol.md`) is:

  ```
  request:  {"model": ..., "input": ...}          (always)
            {"tools": [...], "tool_results": [...]} (only when relevant)
  response: {"output": "<text answer>"}
            | {"tool_name": "...", "tool_input": "..."}
  ```

- `Agent.run()` consumes `generate_response()` and runs the loop:
  provider asks for a tool → the agent executes it through the existing
  `ToolRegistry`/`ToolExecutor` → the `ToolResult` is fed back → repeat
  until a `TextResponse` or `max_iterations` (default 10) is reached.
  Tool failures become error `ToolResult`s for the provider instead of
  crashing the run; explicit `execute_tool()` is unchanged.
- `ScriptedProvider` is added so demos and tests exercise the loop
  deterministically, network-free.

## Consequences

- The generic `HttpProvider` stays vendor-neutral and dependency-free;
  adapting a real vendor API means writing a small Provider that speaks the
  NexusAgent shape — a follow-up decision (candidate: OpenAI/Anthropic
  adapters, tracked separately).
- The loop is bounded; a misbehaving backend cannot loop forever.
- Public API addition (`generate_response`, `ToolSpec`, `ToolResult`,
  `ScriptedProvider`) is backward compatible: existing `generate()`-only
  providers keep working through the default implementation.
- Protocol changes now require updating `docs/protocol.md` and the contract
  tests in the same PR.
