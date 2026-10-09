# NexusAgent — Project Status (Snapshot)

Where the project stands and where to resume. Updated for **v0.2.0**.

## Current state: WORKING and STABLE

- `python scripts/check.py` passes: `ruff check`, `ruff format --check`, `mypy` (strict), `pytest` (679 tests).
- Zero third-party runtime dependencies (enforced by a test).
- CI runs the same check on Python 3.10–3.13, Linux and Windows (`.github/workflows/ci.yml`).

## What NexusAgent can do today

- **Autonomous tool-calling loop.** `Agent.run()` asks the provider; on a tool-call response it runs the tool, feeds the result back, and repeats until a text answer or `max_steps`. Tool errors are returned to the model as `error: …` rather than aborting the run.
- **Providers:** `fake` (offline), `http` (generic JSON backend), `openai` (any OpenAI-compatible Chat Completions API, including Ollama / LM Studio / vLLM / OpenRouter), `anthropic` (Messages API). `ScriptedProvider` replays canned responses for tests/demos.
- **Conversations:** `Runtime.conversation()` keeps multi-turn history (tool turns included); failed turns are discarded.
- **CLI:** one-shot runs, interactive `chat`, `tool list|run`, `--provider/--model/--max-steps/--system/-v`.
- **Settings:** `NEXUS_*` env vars including `NEXUS_SYSTEM_PROMPT` and `NEXUS_MAX_STEPS`.

## Decisions taken (these resolved the old blocker)

- The generic HTTP wire format is NexusAgent's own: response is `{"output": …}` *or* `{"tool_name", "tool_input", "call_id"?}`. Real vendor APIs are handled by dedicated providers.
- Tools stay string-in/string-out. They are advertised to function-calling APIs as one required string parameter named `input`.
- `Provider.generate(prompt) -> str` is unchanged. `Provider.respond(messages, tools)` is the structured entry point; its default delegates to `generate`, so old providers (even duck-typed ones with only `generate`) keep working.
- Only the first tool call of a multi-call model response is handled per step (the model re-requests the rest).
- `CalculatorTool` deliberately stays single-operation (`number op number`); its tests lock this.

## Known limitations / good next steps

1. **Streaming** responses (providers currently return whole messages).
2. **Async** API (everything is synchronous, `urllib`-based).
3. **Retries / backoff** for transient HTTP errors (429/5xx). Errors currently report only the status code, by design (no response bodies, so keys can't leak).
4. **Richer built-in tools** (time, file read in a sandbox, HTTP fetch, web search) and tools with structured (multi-parameter) input.
5. **Persistent memory** — `Conversation` is in-memory only; add save/load.
6. **`max_tokens`** for Anthropic is a constant (4096); make it configurable.
7. **Publish to PyPI** once the API settles (see CONTRIBUTING for the release checklist).

## How to run things

```bash
pip install -e ".[dev]"
python scripts/check.py                       # everything CI runs
python -m pytest                              # tests only
python examples/tool_loop_offline.py          # see the loop with no network
python -m nexusagent chat                     # interactive
```
