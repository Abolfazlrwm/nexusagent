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
  scattering, not an echo), and since v1.8.0 a keyword-scored
  knowledge sheet beside it: chess, space, the human body, everyday
  science (``"who moves first in chess?"`` gets "white", not a shrug).
- **Near misses get did-you-mean**: a noun or topic that is close to
  something on the sheets is named back (``"what color is the skys?"``
  suggests the sky), so a miss teaches the visitor what to ask next.
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
from difflib import get_close_matches
from typing import NamedTuple

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

_SKY_ANSWER = (
    "Blue. Air molecules scatter short blue wavelengths of sunlight far "
    "more strongly than longer red ones — Rayleigh scattering. Near sunset "
    "the light crosses much more atmosphere, the blues scatter away along "
    "the way, and reds and oranges take over."
)

_FACTS: dict[str, str] = {
    "sky": _SKY_ANSWER,
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


class _Knowledge(NamedTuple):
    """One entry of the knowledge sheet: its label, triggers and answer."""

    topic: str
    keywords: tuple[str, ...]
    answer: str


# The knowledge sheet (v1.8.0, ADR 0017): closed, deterministic, factual.
# Matching scores keyword hits — the entry with the most distinct hits
# wins, ties stay with the earlier entry, so order is part of the design:
# more specific entries first. Keywords are lowercase words or phrases
# matched on word boundaries against the user's last line.
_KNOWLEDGE: tuple[_Knowledge, ...] = (
    _Knowledge(
        "chess",
        ("chess", "checkmate", "gambit", "castling"),
        "White moves first. Every standard chess game opens with a move by "
        "white and the players alternate from there — black never starts.",
    ),
    _Knowledge(
        "why the sky is blue",
        ("why is the sky", "why the sky", "sky blue", "blue sky"),
        _SKY_ANSWER,
    ),
    _Knowledge(
        "the speed of light",
        (
            "speed of light",
            "light speed",
            "lightspeed",
            "how fast is light",
            "how fast does light",
        ),
        "Exactly 299,792,458 metres per second in vacuum — a fixed constant "
        "of nature (the metre is defined from it). Through air or water it "
        "runs slightly slower, and nothing with mass ever reaches it.",
    ),
    _Knowledge(
        "how far the sun is",
        (
            "far is the sun",
            "far the sun",
            "distance to the sun",
            "sun distance",
        ),
        "About 149.6 million kilometres on average — one astronomical unit. "
        "Sunlight needs roughly 8 minutes and 20 seconds to make the trip.",
    ),
    _Knowledge(
        "how far the moon is",
        (
            "far is the moon",
            "far the moon",
            "distance to the moon",
            "moon distance",
        ),
        "About 384,400 kilometres on average — roughly 1.3 light-seconds, "
        "or thirty Earth diameters laid side by side.",
    ),
    _Knowledge(
        "the boiling point of water",
        (
            "boiling point",
            "boiling water",
            "water boil",
            "water boils",
            "boil water",
        ),
        "100 °C (212 °F) at sea level. The point follows the pressure: about "
        "95 °C in Denver, about 70 °C on Everest, and above 100 °C inside a "
        "pressure cooker.",
    ),
    _Knowledge(
        "normal body temperature",
        ("body temperature", "normal temperature", "fever"),
        "About 37 °C (98.6 °F) for a healthy adult, with a normal day-long "
        "spread of roughly 36.1-37.2 °C. Above 38 °C is usually called a fever.",
    ),
    _Knowledge(
        "pi",
        ("pi", "circumference"),
        "π ≈ 3.141592653589793 — a circle's circumference divided by its "
        "diameter. It is irrational: the digits never end and never repeat.",
    ),
    _Knowledge(
        "how long a year is",
        (
            "leap year",
            "days in a year",
            "days are in a year",
            "days does a year",
            "how long is a year",
        ),
        "365 days, and 366 in a leap year. Leap years come every fourth year "
        "— but centuries are skipped unless divisible by 400 (2000 was one, "
        "1900 wasn't).",
    ),
    _Knowledge(
        "how many continents there are",
        ("continent", "continents"),
        "Seven: Asia, Africa, North America, South America, Antarctica, Europe and Australia.",
    ),
    _Knowledge(
        "the oceans",
        ("ocean", "oceans", "pacific"),
        "Five named basins — Pacific, Atlantic, Indian, Southern and Arctic. "
        "The Pacific is the largest: about 165 million km², larger than all "
        "the land on Earth combined.",
    ),
    _Knowledge(
        "the planets",
        ("planet", "planets", "solar system", "pluto"),
        "Eight, from Mercury out to Neptune. Pluto was reclassified as a "
        "dwarf planet in 2006 — there are five named dwarf planets today.",
    ),
    _Knowledge(
        "the tallest mountain",
        ("everest", "tallest mountain", "highest mountain", "mountain"),
        "Mount Everest — 8,849 metres above sea level, on the Nepal-China "
        "border. (Mauna Kea is taller base-to-peak, but most of it hides "
        "under the Pacific.)",
    ),
    _Knowledge(
        "the largest animal",
        ("largest animal", "biggest animal", "blue whale", "whale"),
        "The blue whale — up to about 30 metres and 150 tonnes, the largest "
        "animal alive today. Its heart alone weighs around 180 kilograms.",
    ),
    _Knowledge(
        "the fastest land animal",
        ("fastest land", "cheetah"),
        "The cheetah — around 100 km/h in short bursts of a few hundred "
        "metres, steering with its tail at full sprint.",
    ),
    _Knowledge(
        "how many bones a human has",
        ("bones", "bone", "skeleton"),
        "206 in an adult. Babies start with roughly 270-300 and many fuse "
        "together as you grow — which is why the numbers shrink.",
    ),
)

# Near-miss suggestions (v1.8.0): single lowercase words mapped to the
# display name of the sheet topic they stand for. ``difflib`` does the
# matching, deterministically.
_TOPIC_DISPLAY: dict[str, str] = {
    "chess": "chess",
    "speed": "the speed of light",
    "light": "the speed of light",
    "sun": "how far the sun is",
    "moon": "how far the moon is",
    "boil": "the boiling point of water",
    "boiling": "the boiling point of water",
    "pi": "pi",
    "leap": "how long a year is",
    "continent": "how many continents there are",
    "continents": "how many continents there are",
    "ocean": "the oceans",
    "oceans": "the oceans",
    "pacific": "the oceans",
    "planet": "the planets",
    "planets": "the planets",
    "everest": "the tallest mountain",
    "mountain": "the tallest mountain",
    "whale": "the largest animal",
    "cheetah": "the fastest land animal",
    "bone": "how many bones a human has",
    "bones": "how many bones a human has",
    "skeleton": "how many bones a human has",
    "fever": "normal body temperature",
    "body": "normal body temperature",
    "sky": "the sky",
    "sunset": "the sunset",
    "grass": "grass",
    "leaf": "leaves",
    "leaves": "leaves",
    "blood": "blood",
    "banana": "a banana",
    "snow": "snow",
    "rose": "a rose",
}
_SUGGESTION_WORDS = tuple(_TOPIC_DISPLAY)

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
    "Five honest tricks, all offline: run the calculator through the real "
    "tool loop (ask me for 144 / 12), remember your name across runs, "
    "answer a small fact sheet — colors, chess, space, the human body "
    "(try: what color is the sky? or who moves first in chess?) — suggest "
    "close topics when I miss, and stream my answers word by word. For "
    "open-ended questions, wire a real provider — OpenAI, Anthropic or "
    "Gemini are built in."
)

_FALLBACK_REPLY = (
    "That's beyond my offline fact sheet — no API keys, no network, so I "
    "won't guess. DemoProvider is deterministic: it does math through the "
    "calculator tool, remembers your name, answers a small fact sheet "
    "(try: what color is the sky? or who moves first in chess?), and "
    "streams word by word. For open-ended questions, wire one of the "
    "built-in real providers: OpenAI, Anthropic or Gemini — see the README."
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

        knowledge = self._knowledge_lookup(text)
        if knowledge is not None:
            return TextResponse(knowledge)

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

        suggestion = self._suggestion(text)
        if suggestion is not None:
            return TextResponse(
                f"Nothing on my sheet for that — did you mean {suggestion}? " + _FALLBACK_REPLY
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
        close = get_close_matches(noun, sorted(_FACTS), n=1, cutoff=0.75)
        if close:
            return (
                f"I keep an offline fact sheet, and {noun!r} isn't on it — "
                f"did you mean {close[0]!r}? On the sheet: the sky, the sun, "
                "grass, blood, snow. Or plug in a real provider for "
                "open-ended questions."
            )
        return (
            f"I keep an offline fact sheet, and {noun!r} isn't on it yet — no "
            "API keys, no network, so I can't look it up. On the sheet: the "
            "sky, the sun, grass, blood, snow. Or plug in a real provider for "
            "open-ended questions."
        )

    def _knowledge_lookup(self, text: str) -> str | None:
        """Score the knowledge sheet: most keyword hits wins, ties stay first."""
        normalized = text.lower()
        best: _Knowledge | None = None
        best_score = 0
        for entry in _KNOWLEDGE:
            score = sum(
                1
                for keyword in entry.keywords
                if re.search(rf"\b{re.escape(keyword)}\b", normalized) is not None
            )
            if score > best_score:
                best, best_score = entry, score
        return best.answer if best is not None else None

    def _suggestion(self, text: str) -> str | None:
        """A close sheet topic for the prompt, if the words nearly touch one."""
        for word in re.findall(r"[a-z]{3,}", text.lower()):
            close = get_close_matches(word, _SUGGESTION_WORDS, n=1, cutoff=0.75)
            if close:
                return _TOPIC_DISPLAY[close[0]]
        return None
