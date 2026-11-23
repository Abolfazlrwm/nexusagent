# ADR 0017 — The demo brain knowledge sheet

- Status: accepted
- Date: 2026-11-23
- Relates to: 0016 (offline demo provider), 0002 (tool loop), 0009 (streaming), 0010 (stability), 0015 (orchestration)

## Context

ADR 0016 shipped `DemoProvider` so the real Agent loop runs with zero API
keys — and its first contact with real users immediately showed the gap.
The browser demo advertises a free-form prompt box; a visitor typed
**"who start first in chess? black or white"** and received the honest
fallback: that this brain has no fact sheet entry for chess, no API keys,
no network, and a pointer at real providers. Truthful — and still a
dead end. The fallback names what the provider *can't* do; the visitor
never learns what it *can*.

Two more gaps surfaced in the same experiment:

1. The fact sheet answered only **"what color is X?"** phrasings. The
   single most common phrasing of the most famous fact on the sheet —
   *"why is the sky blue?"* — missed it entirely.
2. When the sheet missed, the reply was static. A near miss ("what color
   is the skys?") and a topic miss ("tell me about the moon landing")
   both got the same generic text, teaching the visitor nothing about
   what the sheet *does* hold.

## Decision

Grow the demo brain from one color sheet to three layers behind the same
`generate_response` contract, still deterministic, still offline, still
zero-dependency — and still `DemoProvider`, with **no public surface
change** (the root stays at 41 names, additive-only per ADR 0010).

1. **The knowledge sheet** (new). A table of `_Knowledge(topic, keywords,
   answer)` entries covering closed, verifiable, everyday questions:
   chess (white moves first), why the sky is blue, the speed of light,
   the sun/moon distances, the boiling point of water, body temperature,
   pi, year length and leap-year rules, continents, oceans, planets,
   Everest, the blue whale, the cheetah, human bones. Matching scores
   **distinct keyword hits** per entry (lowercase, word-boundary); the
   highest score wins, ties stay with the earlier entry — so entry order
   is part of the design, and every lookup is byte-reproducible.
2. **"Why" phrasings route to the same answer.** The knowledge entry for
   the sky shares one `_SKY_ANSWER` constant with the color sheet, so
   "what color is the sky?" and "why is the sky blue?" return the
   identical Rayleigh-scattering explanation.
3. **Did-you-mean on every miss.** On a color-sheet miss,
   `difflib.get_close_matches` suggests the closest known noun
   ("skys" → "sky"); on a total miss, the closest topic word
   ("moon landing" → "how far the moon is"). Suggestions are appended to
   the honest fallback, never replacing it. A prompt whose words touch
   no topic produces the unchanged plain fallback — which stays a pinned
   constant, byte-stable and test-asserted.

The fallback itself now advertises the new reach: it names chess as an
example question, so the next visitor types a question the brain can
actually answer.

## Consequences

- The visitor's first question is far more likely to get a real answer,
  and every miss now teaches the sheet's vocabulary instead of dead-ending.
- Determinism holds everywhere: keyword scoring, `difflib` matching and
  entry ordering are all deterministic, so the browser demo stays
  byte-reproducible and CI can pin every answer byte-for-byte.
- The sheet stays **closed on purpose**. It is a demonstration aid, not
  an encyclopedia: every entry is verified, every answer is test-pinned.
  Growing it is additive and reviewable.
- The honest fallback remains the contract boundary: anything the sheets
  do not know is answered by naming what exists (math, memory, fact
  sheets, streaming) and which real providers to wire next — never by
  inventing facts.

## Rejected alternatives

- **A regex per question type** (the 1.7.0 style): fifteen topics would
  mean dozens of near-duplicate patterns ("who starts/moves/begins first
  in chess"), each a maintenance liability. Keyword scoring replaces the
  zoo with one table.
- **Fuzzy-matching the sheet directly** (no exact layer): attractive,
  but it would turn "what color is the skys?" into an answer about the
  sky *silently*. Determinism stays crisper when exact hits are exact
  and only misses consult the fuzzy layer.
- **Shipping a tiny embedded model or encyclopedia**: violates the
  zero-dependency, zero-network, deterministic contract that makes the
  demo brain auditable — and a hallucinating demo is worse than an
  honest miss.
