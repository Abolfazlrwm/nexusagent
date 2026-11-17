"""In-process conversation memory (ADR 0012).

NexusAgent runs stateless: every ``Agent.run()`` call starts a fresh tool
loop and the Provider never sees what happened in earlier runs. Memory is
the opt-in way to close that gap: completed turns (the user input and the
final assistant answer of each successful run) are recorded and composed
into the prompt of the next run, so the model can carry context across
runs — names, decisions, earlier results.

The design is deliberately provider-agnostic: the Agent composes the
remembered turns into a text transcript it prepends to the user input
(:func:`compose_prompt`), and the Provider contract is untouched. Any
Provider works with memory unchanged — the four built-in HTTP adapters as
well as user-written subclasses — because nothing new crosses the
Provider boundary. With an empty memory the composed prompt is the input
byte-for-byte, so configuring memory never changes a first run.

Storage ships in two flavors: a process-local, bounded FIFO
(:class:`InMemoryMemory`) and a persistent backend backed by a local
SQLite database file (:class:`SQLiteMemory`) — both dependency-free.
Custom backends (Redis, PostgreSQL, ...) implement the three-method
:class:`Memory` ABC.
"""

from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType

from nexusagent.logging import get_logger

__all__ = ["ConversationTurn", "InMemoryMemory", "Memory", "SQLiteMemory"]

USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"
VALID_ROLES = (USER_ROLE, ASSISTANT_ROLE)

DEFAULT_MAX_TURNS = 100

_TRANSCRIPT_HEADER = "Previous conversation (oldest first):"
_USER_PREFIX = f"{USER_ROLE}: "
_ASSISTANT_PREFIX = f"{ASSISTANT_ROLE}: "
_NEW_MESSAGE_INTRO = "Respond to this new user message:"

_logger = get_logger("nexusagent.memory")


@dataclass(frozen=True)
class ConversationTurn:
    """One completed conversation turn, recorded by the Agent.

    ``role`` is ``"user"`` or ``"assistant"`` and ``text`` is the full
    turn content. Instances are immutable; a turn is recorded once and
    never rewritten.
    """

    role: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, str):
            raise TypeError("role must be a string")

        if self.role not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}, got {self.role!r}")

        if not isinstance(self.text, str):
            raise TypeError("text must be a string")


class Memory(ABC):
    """Contract for storing completed conversation turns (ADR 0012).

    Implement this ABC to replace the built-in :class:`InMemoryMemory`
    with a custom backend. Implementations are read and written by the
    Agent around each successful run; they are not accessed concurrently
    by the runtime itself, so a simple in-process implementation is
    enough for the sync and async agents alike.
    """

    @abstractmethod
    def append(self, turn: ConversationTurn) -> None:
        """Record one completed conversation turn."""

    @abstractmethod
    def history(self) -> tuple[ConversationTurn, ...]:
        """Return the remembered turns, oldest first."""

    @abstractmethod
    def clear(self) -> None:
        """Forget every remembered turn."""

    def __len__(self) -> int:
        return len(self.history())


class InMemoryMemory(Memory):
    """Bounded, process-local FIFO of conversation turns.

    When ``max_turns`` turns are already stored, appending a new one
    evicts the oldest so the bound is never exceeded — long sessions
    cost a fixed amount of memory, and the transcript the next run sees
    always carries the most recent context. ``max_turns`` defaults to
    :data:`DEFAULT_MAX_TURNS` and must be a whole number of at least 1.
    """

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise TypeError("max_turns must be an integer")

        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")

        self._max_turns = max_turns
        self._turns: list[ConversationTurn] = []

    def append(self, turn: ConversationTurn) -> None:
        if not isinstance(turn, ConversationTurn):
            raise TypeError("turn must be a ConversationTurn")

        self._turns.append(turn)
        if len(self._turns) > self._max_turns:
            del self._turns[: len(self._turns) - self._max_turns]
            _logger.debug("memory evicted turns beyond the cap of %d", self._max_turns)

    def history(self) -> tuple[ConversationTurn, ...]:
        return tuple(self._turns)

    def clear(self) -> None:
        self._turns.clear()


class SQLiteMemory(Memory):
    """Conversation memory persisted in a local SQLite database (ADR 0013).

    A drop-in :class:`Memory` backend for durability beyond the current
    process: turns live in a ``turns`` table of a SQLite database at
    ``path`` (created on first use — missing parent directories are
    created too), so history survives restarts and runtimes that open the
    same file one after another see the same turns. Storage stays
    dependency-free: ``sqlite3`` ships with Python.

    The bounded-FIFO semantics match :class:`InMemoryMemory`: ``max_turns``
    (default :data:`DEFAULT_MAX_TURNS`, validated the same way) caps the
    stored turns and the *oldest rows are deleted* when the cap is
    exceeded — the eviction itself is persisted. Every mutation commits
    immediately. One ``sqlite3`` connection is opened for the lifetime of
    the instance; the runtime never accesses it concurrently and the
    instance is not thread-safe. Call :meth:`close` — or use the instance
    as a context manager — when done; further use of a closed instance
    raises :class:`sqlite3.ProgrammingError`.
    """

    def __init__(self, path: str | os.PathLike[str], max_turns: int = DEFAULT_MAX_TURNS) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int):
            raise TypeError("max_turns must be an integer")

        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")

        self._path = os.fspath(path)
        if not self._path:
            raise ValueError("path must not be empty")

        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._max_turns = max_turns
        self._conn = sqlite3.connect(self._path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS turns ("
            "id INTEGER PRIMARY KEY, "
            "role TEXT NOT NULL, "
            "text TEXT NOT NULL)"
        )
        self._conn.commit()

    @property
    def path(self) -> str:
        """The database file this memory persists to."""
        return self._path

    def append(self, turn: ConversationTurn) -> None:
        if not isinstance(turn, ConversationTurn):
            raise TypeError("turn must be a ConversationTurn")

        self._conn.execute(
            "INSERT INTO turns (role, text) VALUES (?, ?)",
            (turn.role, turn.text),
        )
        self._prune()
        self._conn.commit()

    def history(self) -> tuple[ConversationTurn, ...]:
        rows = self._conn.execute("SELECT role, text FROM turns ORDER BY id ASC").fetchall()
        return tuple(ConversationTurn(role=role, text=text) for role, text in rows)

    def clear(self) -> None:
        self._conn.execute("DELETE FROM turns")
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> SQLiteMemory:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _prune(self) -> None:
        row = self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()
        count = row[0] if row is not None else 0
        excess = count - self._max_turns
        if excess > 0:
            self._conn.execute(
                "DELETE FROM turns WHERE id IN (SELECT id FROM turns ORDER BY id ASC LIMIT ?)",
                (excess,),
            )
            _logger.debug("memory evicted %d turns beyond the cap of %d", excess, self._max_turns)


def compose_prompt(input_text: str, history: Sequence[ConversationTurn]) -> str:
    """Compose the prompt the Provider actually sees for this run.

    With an empty history this is ``input_text`` byte-for-byte — the
    no-memory behavior is unchanged. With remembered turns the transcript
    is prepended oldest first, one ``role: text`` line per turn, followed
    by the new user message; the Provider therefore always sees one
    self-contained prompt, whatever backend it talks to.
    """
    if not history:
        return input_text

    lines = [_TRANSCRIPT_HEADER]
    for turn in history:
        prefix = _USER_PREFIX if turn.role == USER_ROLE else _ASSISTANT_PREFIX
        lines.append(f"{prefix}{turn.text}")
    lines.append("")
    lines.append(_NEW_MESSAGE_INTRO)
    lines.append(input_text)
    return "\n".join(lines)
