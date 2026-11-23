"""The offline demo brain (ADR 0016).

:class:`DemoProvider` is a deterministic, network-free stand-in brain
shipped with the runtime. It exists so a demo, a quickstart or a
classroom can run the real :class:`~nexusagent.agent.Agent` — bounded
tool loop, conversation memory, streaming — with **zero API keys** and
still get answers that are worth reading, instead of a canned echo.

What it does, honestly:

- **Math** goes through the real tool loop: with a ``calculator`` tool
  advertised, a prompt like ``"what is 144 / 12?"`` produces a
  :class:`~nexusagent.provider.ToolCallRequest`, the Agent executes the
  tool, and the fed-back result is phrased into an answer.
- **A small fact sheet** answers a few closed questions exactly —
  colors chief among them (``"what color is the sky?"`` gets Rayleigh
  scattering, not an echo).
- **Name memory** works across runs: ``"my name is Sara"`` now, ``"what
  is my name?"`` later — the remembered name is recovered from the
  composed transcript (the provider has not opted into native history
  threading, ADR 0014, so memory arrives composed into the prompt).
- **Everything else** gets a truthful fallback that says what this
  provider is, what it can do, and which real providers to wire next.

It is deterministic by contract: the same prompt (and tool state) always
produces the same answer, which makes demos reproducible and testable.
It is a demonstration aid, not a model — open-ended questions need one
of the built-in real providers (OpenAI ADR 0005, Anthropic ADR 0007,
Gemini ADR 0008).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

from nexusagent.provider import (
    Provider,
    ProviderResponse,
    ProviderStreamEvent,
    StreamTextDelta,
    TextResponse,
    ToolCallRequest,
    ToolResult,
    ToolSpec,
)

_MATH = re.compile(r"(-?\d+(?:\.\d+)?(?:\s*[+\-*/]\s*-?\d+(?:\.\d+)?)+)")
_NAME = re.compile(r"\bmy name is ([A-Za-z]+)\b", re.IGNORECASE)
_REMEMBERED_NAME = re.compile(r"\buser:.*?\bmy name is ([A-Za-z]+)\b", re.IGNORECASE)
_WHO = re.compile(r"what(?:'s| is) my name|who am i\b", re.IGNORECASE)
_GREETING = re.compile(r"^\s*(?:hi|hello|hey)\b", re.IGNORECASE)
_IDENTITY = re.compile(r"who are you|what are you|introduce yourself", re.IGNORECASE)
_CAPABILITIES = re.compile(r"what can you do|what do you do|^\s*help\s*$", re.IGNORECASE)
_HOW_ARE_YOU = re.compile(r"how are you", re.IGNORECASE)
_THANKS = re.compile(r"\b(?:thanks|thank you)\b", re.IGNORECASE)
_FAREWELL = re.compile(r"\b(?:bye|goodbye|see you)\b", re.IGNORECASE)
_JOKE = re.compile(r"\bjoke\b", re.IGNORECASE)
_COLOR_IS = re.compile(
    r"what\s+(?:color|colour)\s+is\s+(?:a\s+|an\s+|the\s+)?([a-z][a-z ]*?)\??\s*$", re.IGNORECASE
)
_COLOR_OF = re.compile(
    r"what(?:'s| is)\s+the\s+(?:color|colour)\s+of\s+(?:a\s+|an\s+|the\s+)?([a-z][a-z ]*?)\??\s*$",
    re.IGNORECASE,
)
_AGENT_BULLET = re.compile(r"^- (.+)$", re.MULTILINE)
_ROUTER_MARK = re.compile(r"Answer with exactly one agent name", re.IGNORECASE)

_FACTS: dict[str, str] = {
    "sky": (
        "Blue. Air molecules scatter short blue wavelengths of sunlight far "
        "more strongly than longer red ones — Rayleigh scattering. Near sunset "
        "the light crosses much more atmosphere, the blues scatter away along "
        "the way, and reds and oranges take over."
    ),
    "sunset": (
        "Reds and oranges. Near the horizon sunlight crosses much more "
        "atmosphere; blues scatter away along the way, leaving the long "
        "wavelengths to reach your eye."
    ),
    "sunset sky": (
        "Reds and oranges. Near the horizon sunlight crosses much more "
        "atmosphere; blues scatter away along the way, leaving the long "
        "wavelengths to reach your eye."
    ),
    "evening sky": (
        "Reds and oranges. Near the horizon sunlight crosses much more "
        "atmosphere; blues scatter away along the way, leaving the long "
        "wavelengths to reach your eye."
    ),
    "sun": (
        "White. Sunlight actually peaks in the green-blue part of the "
        "spectrum; Earth's atmosphere plus the eye's sensitivity make it look "
        "yellow from the ground."
    ),
    "grass": (
        "Green. Chlorophyll absorbs red and blue light for photosynthesis and "
        "reflects the green part — which is what reaches your eye."
    ),
    "leaf": (
        "Green. Chlorophyll absorbs red and blue light for photosynthesis and "
        "reflects the green part — which is what reaches your eye."
    ),
    "leaves": (
        "Green while chlorophyll dominates; in autumn it breaks down and the "
        "yellow and orange carotenoids that were there all along show through."
    ),
    "blood": (
        "Red. Hemoglobin's iron-containing pigment absorbs light in a way "
        "that leaves red to reflect back — bright red when oxygen-rich, "
        "darker when oxygen-poor."
    ),
    "banana": (
        "Yellow when ripe — carotenoid pigments. Unripe ones look green "
        "because chlorophyll still dominates, and overripe ones brown as "
        "pigments oxidize."
    ),
    "snow": (
        "White. Ice crystals scatter all visible wavelengths roughly equally, "
        "so the mixture reflects back as white even though each crystal is "
        "transparent."
    ),
    "rose": (
        "Mostly reds and pinks — anthocyanin pigments. Breeding has produced "
        "roses in nearly every color except a true blue."
    ),
}

_GREETING_REPLY = (
    "Hello! I'm NexusAgent's offline demo brain — deterministic, no API "
    "keys, no network. Try a math question, ask what color the sky is, or "
    "tell me your name."
)

_IDENTITY_REPLY = (
    "I'm DemoProvider — the offline stand-in brain shipped with "
    "NexusAgent. Behind me runs the real Agent loop: a bounded tool loop "
    "(ADR 0002), conversation memory (ADR 0012) and streaming (ADR 0009). "
    "Same prompt in, same answer out — fully deterministic."
)

_CAPABILITIES_REPLY = (
    "Four honest tricks, all offline: run the calculator through the real "
    "tool loop (ask me for 144 / 12), remember your name across runs, "
    "answer a small fact sheet (try: what color is the sky?), and stream "
    "my answers word by word. For open-ended questions, wire a real "
    "provider — OpenAI, Anthropic or Gemini are built in."
)

_FALLBACK_REPLY = (
    "That's beyond my offline fact sheet. DemoProvider is deterministic "
    "and network-free — no API keys anywhere. I do math through the "
    "calculator tool, name memory across runs, a few color facts (try: "
    "what color is the sky?), and word-by-word streaming. For open-ended "
    "questions, wire one of the built-in real providers: OpenAI, "
    "Anthropic or Gemini — see the README."
)


def _last_line(prompt: str) -> str:
    """The user's own words: the final line of the (composed) prompt."""
    return prompt.strip().splitlines()[-1].strip()


class DemoProvider(Provider):
    """A deterministic, network-free stand-in brain for demos (ADR 0016).

    Implements the full sync :class:`~nexusagent.provider.Provider`
    contract: ``generate()`` for plain completions (and for
    ``create_provider_router``), ``generate_response()`` for the tool
    loop, and ``stream_response()`` yielding word-by-word deltas before
    the final answer. Every call is counted in ``calls``.
    """

    def __init__(self) -> None:
        self.calls = 0

    # -- plain completions -------------------------------------------------

    def generate(self, prompt: str) -> str:
        """Answer with plain text — no tools, no loop.

        When the prompt is a ``create_provider_router`` decision request
        (it lists agent names and asks for exactly one), the reply picks
        a listed name deterministically: an agent name the user prompt
        itself mentions wins; otherwise the first listed name. That
        keeps an :class:`~nexusagent.orchestration.AgentTeam` runnable
        fully offline, while real routing semantics stay the job of a
        real provider.
        """
        if _ROUTER_MARK.search(prompt):
            names: list[str] = _AGENT_BULLET.findall(prompt)
            user_prompt = ""
            user = re.search(r"User prompt:\n(.*)$", prompt, re.DOTALL)
            if user:
                user_prompt = user.group(1).lower()
            for name in names:
                if re.search(rf"\b{re.escape(name.lower())}\b", user_prompt):
                    return name
            if names:
                return names[0]

        response = self.generate_response(prompt)
        return response.text if isinstance(response, TextResponse) else response.tool_name

    # -- the tool loop contract --------------------------------------------

    def generate_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> ProviderResponse:
        """Answer for the bounded tool loop, offline.

        A fed-back tool result is phrased into an answer; otherwise a
        math request with a ``calculator`` tool advertised produces a
        :class:`~nexusagent.provider.ToolCallRequest` (the loop takes
        over); otherwise the fact sheet and the honest fallback answer
        in text. ``history`` is accepted for the 1.5 Provider contract
        (ADR 0014) and is deliberately unused: this provider has not
        opted into native history threading, so remembered turns arrive
        composed into ``prompt``.
        """
        self.calls += 1

        if tool_results:
            return self._summarize(tool_results[-1])

        text = _last_line(prompt)

        match = _MATH.search(text)
        if match and any(t.name == "calculator" for t in tools):
            expression = text if _MATH.fullmatch(text) else match.group(0)
            return ToolCallRequest("calculator", expression)
        if match:
            return TextResponse(
                f"I can compute {match.group(0)!r} — give me the calculator "
                "tool and I'll run it through the real tool loop."
            )

        fact = self._fact_sheet(text)
        if fact is not None:
            return TextResponse(fact)

        remembered = _REMEMBERED_NAME.findall(prompt)
        if _WHO.search(text) and remembered:
            return TextResponse(f"Your name is {remembered[-1]} — remembered from an earlier run.")
        if _WHO.search(text):
            return TextResponse("I don't know your name yet — tell me first.")

        name = _NAME.search(text)
        if name:
            return TextResponse(f"Nice to meet you, {name.group(1)}! I'll remember your name.")

        if _GREETING.match(text):
            return TextResponse(_GREETING_REPLY)
        if _IDENTITY.search(text):
            return TextResponse(_IDENTITY_REPLY)
        if _CAPABILITIES.search(text):
            return TextResponse(_CAPABILITIES_REPLY)
        if _HOW_ARE_YOU.search(text):
            return TextResponse(
                "Deterministic and covered by tests — every call with the "
                "same input returns the same answer. That's my kind of "
                "reliability."
            )
        if _THANKS.search(text):
            return TextResponse("You're welcome — happy to demo.")
        if _FAREWELL.search(text):
            return TextResponse("Goodbye — the demo restarts fresh whenever you reload.")
        if _JOKE.search(text):
            return TextResponse(
                "Why did the agent stop mid-thought? It hit its step budget — "
                "every good tool loop is bounded."
            )

        return TextResponse(_FALLBACK_REPLY)

    def stream_response(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolSpec] = (),
        tool_results: Sequence[ToolResult] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> Iterator[ProviderStreamEvent]:
        """Stream the answer word by word (ADR 0009), offline.

        Yields one :class:`~nexusagent.provider.StreamTextDelta` per
        whitespace-separated word (each carrying its trailing space),
        then the final complete ``TextResponse``. Tool-call answers are
        not streamable; they surface as the single final event.
        """
        response = self.generate_response(prompt, tools=tools, tool_results=tool_results)
        if isinstance(response, TextResponse):
            for word in response.text.split(" "):
                yield StreamTextDelta(word + " ")
        yield response

    # -- helpers -----------------------------------------------------------

    def _summarize(self, result: ToolResult) -> ProviderResponse:
        """Phrase a fed-back tool result into the final answer."""
        if result.is_error:
            return TextResponse(f"The {result.tool_name} tool failed: {result.output}")
        if result.tool_name == "calculator":
            return TextResponse(f"{result.tool_input} equals {result.output}.")
        return TextResponse(f"The {result.tool_name} tool returned {result.output}.")

    def _fact_sheet(self, text: str) -> str | None:
        """Look ``text`` up in the small color fact sheet, if it fits."""
        match = _COLOR_IS.search(text) or _COLOR_OF.search(text)
        if not match:
            return None
        noun = " ".join(match.group(1).lower().split()).rstrip(".,!?:;")
        fact = _FACTS.get(noun)
        if fact is not None:
            return fact
        return (
            f"I keep an offline fact sheet, and {noun!r} isn't on it yet — no "
            "API keys, no network, so I can't look it up. On the sheet: the "
            "sky, the sun, grass, blood, snow. Or plug in a real provider for "
            "open-ended questions."
        )
