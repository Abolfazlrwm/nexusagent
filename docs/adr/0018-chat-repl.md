# ADR 0018 — `nexusagent chat`: the offline chat REPL

- Status: accepted
- Date: 2026-11-23
- Relates to: 0002 (tool loop), 0009 (streaming), 0012 (memory), 0016/0017 (demo brain), 0010 (stability)

## Context

The runtime had two ways to be felt: the browser demo and the one-shot
`nexusagent "prompt"` command. Both work, but neither is a *conversation* —
the thing an agent runtime is for. A newcomer installing the package had no
ten-second path from `pip install` to an actual back-and-forth with real
tool calls and real memory; that path started at "open the browser" or
"copy a code snippet". Every professional CLI library ships its product as
a command a user can type immediately.

Meanwhile the offline demo brain (ADR 0016/0017) had become good enough to
hold a real conversation: it computes through the calculator tool, remembers
names across turns, answers a closed fact sheet, streams word by word —
all deterministic, zero keys, zero network.

## Decision

Add a `chat` subcommand to the existing `nexusagent` console script:

    nexusagent chat                # the offline demo brain (default)
    nexusagent chat --no-stream    # whole answers instead of streamed ones
    nexusagent chat --provider openai   # a real provider from NEXUS_* env

- **One runtime, both worlds.** The default builds a `Runtime` around the
  shipped `DemoProvider` plus the real tool registry, executor and an
  `InMemoryMemory(max_turns=16)` — the same wiring the browser demo uses.
  `--provider NAME` builds through `create_application_runtime` from the
  `NEXUS_*` environment exactly like the one-shot command, so configuration
  problems surface as clear `ValueError`s *before* any network call.
- **A thin, testable loop.** `run_chat_repl` takes injected input and output
  callables; whole conversations run in tests without a terminal. EOF and
  `Ctrl+C` end the session gracefully; empty lines cost nothing.
- **Commands, not magic**: `/help`, `/reset` (clears the conversation
  memory — and says so honestly when no memory is configured), `/tools`
  (lists the registered tools), `/exit`, `/quit`.
- **Streaming by default** (ADR 0009): answers arrive word by word through
  `on_delta`, exactly as they do in the browser demo and in real providers.
- **No public-surface change.** The root stays at 41 names (ADR 0010);
  `nexusagent.chat` is a module of the CLI layer, not a new public export.

## Consequences

- `pip install nexusagent-runtime && nexusagent chat` is now the zero-config
  quickstart the README can print in one line.
- The demo brain finally has a *conversational* stage: multi-turn math,
  name memory and fact-sheet questions in one session, streamed live.
- Real providers are one flag away, with the same environment contract as
  everywhere else in the runtime — no second configuration system.

## Rejected alternatives

- **A separate `nexusagent-chat` console script**: two entry points for one
  binary is worse than one entry point with subcommands; `nexusagent chat`
  reads like every professional CLI.
- **Building the REPL on `create_application_runtime` only** (a `demo`
  Settings provider): would either grow the settings surface or fake the
  demo brain through the `fake` provider. The demo brain is a first-class
  provider; the REPL wires it directly, and real providers keep the
  settings path.
- **A readline/pty dependency**: violates the zero-dependency contract for
  marginal polish; plain `input()` with injected callables is testable
  anywhere.
