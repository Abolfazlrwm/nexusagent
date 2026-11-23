# ADR 0016 — The offline demo brain (`DemoProvider`)

- Status: accepted
- Date: 2026-11-23
- Relates to: 0002 (tool loop), 0009 (streaming), 0010 (stability), 0012 (memory), 0015 (orchestration)

## Context

Every provider in the runtime answers from somewhere: OpenAI, Anthropic and
Gemini need API keys and a network; `FakeProvider` answers `fake response: …`
and `ScriptedProvider` replays a fixed queue. Both are honest, but neither is
satisfying for the two moments the library actually gets shown to people:

1. **The browser demo** — a visitor types "what color is sky" into the free-form
   prompt box and receives `(scripted model) You said: what color is sky`. That
   is truthful and useless at the same time.
2. **The zero-config quickstart** — there is no way to run the real `Agent`
   loop, with real tool calls and real memory, before someone hands you an API
   key.

What was missing is a provider whose answers are *worth reading*, while staying
deterministic, offline and dependency-free — the same three properties that
make the rest of the runtime auditable.

## Decision

Ship `DemoProvider` as part of the public API (ADR 0010: additive, the root
surface grows 40 → 41). It implements the full sync `Provider` contract and
answers from three layers, in order:

1. **The tool loop.** A fed-back tool result is phrased into an answer. A math
   prompt with a `calculator` tool advertised produces a `ToolCallRequest` —
   the loop, not the provider, does arithmetic. Chain expressions are captured
   whole (`2+2*3`), not two operands at a time. Math without the tool explains
   what is missing instead of pretending.
2. **The fact sheet.** A small closed set of exact answers — colors chief among
   them: the sky (Rayleigh scattering), the sun, grass, leaves, blood, snow,
   bananas, roses, sunsets. Closed on purpose: a fact sheet can be byte-stable
   and test-asserted; a hallucinated encyclopedia cannot.
3. **Small talk and name memory**, then **the honest fallback**: what this
   provider is, what it can do, and which real providers to wire next.

Determinism is the contract: same prompt, same tool state → same answer. That
makes demos reproducible, CI-assertable, and the browser demo byte-identical
for every visitor.

Two cross-feature behaviors are pinned:

- **`generate()` understands the routing decision shape** (ADR 0015). A prompt
  that lists agent names and asks for exactly one gets a listed name: an agent
  name mentioned in the user prompt wins, otherwise the first listed one. An
  `AgentTeam` is therefore runnable fully offline; semantic routing stays the
  job of a real provider.
- **`stream_response()` streams** (ADR 0009): word-by-word `StreamTextDelta`s,
  then the final complete `TextResponse`. Tool-call answers surface as the
  single final event — a tool request is not streamable text.

Name memory works across runs without native-history opt-in (ADR 0014): the
remembered name is recovered from the composed transcript, most recent mention
winning — exactly what a `supports_native_history=False` provider sees.

## Consequences

- The browser demo's free-form prompt box routes through `DemoProvider`;
  visitors now get Rayleigh scattering, real calculator tool calls and
  working name memory — with a visible note that the brain is offline.
- Quickstarts and classrooms run the full loop offline:
  `Agent(DemoProvider(), tool_registry=create_tool_registry(), memory=InMemoryMemory())`.
- The fact sheet is deliberately small. Growing it is additive and boring —
  the moment it would need judgment, the answer belongs to a real provider.
- Root surface 40 → 41 (`DemoProvider`), pinned by `tests/test_public_api.py`.
- Rejected on purpose: making the fact sheet open-ended (that is a model, not
  a provider), and teaching `DemoProvider` about network APIs (it must stay
  dependency-free and offline forever).

## Testing

`tests/test_demo_provider.py` pins every layer: fact-sheet phrasings (including
British spelling and articles), chain-math capture, tool-result phrasing (success,
neutral, failure), name memory across two real `Agent.run` calls with real
`InMemoryMemory`, router-decision `generate()` behavior, streaming event shape,
byte-for-byte determinism, and an end-to-end offline `agent.run("what is 144 / 12?")`
through the real calculator tool.
