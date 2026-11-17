"""Contract tests for the persistent SQLite memory backend (ADR 0013).

SQLiteMemory keeps the exact bounded-FIFO semantics of ``InMemoryMemory``
but stores turns in a local SQLite database file, so history survives
process restarts and runtimes that reopen the same file. These tests pin
the construction and validation contract, the FIFO eviction and its
persistence, ``clear()``, ``close()`` and context-manager behavior,
sharing one database file between instances, and the end-to-end agent
wiring with a reopened memory.
"""

from __future__ import annotations

import dataclasses
import os
import sqlite3
from pathlib import Path

import pytest

from nexusagent import (
    Agent,
    ConversationTurn,
    InMemoryMemory,
    Memory,
    ScriptedProvider,
    SQLiteMemory,
    TextResponse,
    create_runtime,
)
from nexusagent.memory import ASSISTANT_ROLE, USER_ROLE

EXPECTED_TRANSCRIPT = (
    "Previous conversation (oldest first):\n"
    "user: My name is Sara\n"
    "assistant: first answer\n"
    "\n"
    "Respond to this new user message:\n"
    "What is my name?"
)


def turn(role: str, text: str) -> ConversationTurn:
    return ConversationTurn(role, text)


# --- construction and validation -------------------------------------------


def test_is_a_memory_subclass(tmp_path: Path) -> None:
    assert isinstance(SQLiteMemory(tmp_path / "memory.db"), Memory)


def test_accepts_str_and_pathlib_paths(tmp_path: Path) -> None:
    str_path = os.path.join(tmp_path, "a.db")
    string_memory = SQLiteMemory(str_path)
    string_memory.append(turn(USER_ROLE, "hi"))
    assert Path(str_path).is_file()
    string_memory.close()

    path_object = tmp_path / "b.db"
    path_memory = SQLiteMemory(path_object)
    path_memory.append(turn(USER_ROLE, "hi"))
    assert path_object.is_file()
    path_memory.close()


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "deep" / "memory.db"
    memory = SQLiteMemory(db)
    memory.append(turn(USER_ROLE, "hello"))
    assert memory.history() == (turn(USER_ROLE, "hello"),)
    assert db.is_file()
    memory.close()


def test_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="path must not be empty"):
        SQLiteMemory("")


def test_rejects_non_path_arguments() -> None:
    with pytest.raises(TypeError):
        SQLiteMemory(123)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        SQLiteMemory(None)  # type: ignore[arg-type]


def test_path_property_reports_the_database_file(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    assert memory.path == str(tmp_path / "m.db")
    memory.close()


def test_max_turns_rejects_bool(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="max_turns must be an integer"):
        SQLiteMemory(tmp_path / "m.db", max_turns=True)


@pytest.mark.parametrize("value", ["10", 1.5, None])
def test_max_turns_rejects_non_integers(tmp_path: Path, value: object) -> None:
    with pytest.raises(TypeError, match="max_turns must be an integer"):
        SQLiteMemory(tmp_path / "m.db", max_turns=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, -100])
def test_max_turns_rejects_values_below_one(tmp_path: Path, value: int) -> None:
    with pytest.raises(ValueError, match="max_turns must be at least 1"):
        SQLiteMemory(tmp_path / "m.db", max_turns=value)


# --- append / history --------------------------------------------------------


def test_append_rejects_non_turn(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    with pytest.raises(TypeError, match="turn must be a ConversationTurn"):
        memory.append("hello")  # type: ignore[arg-type]


def test_history_round_trips_turns_oldest_first(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    memory.append(turn(USER_ROLE, "first"))
    memory.append(turn(ASSISTANT_ROLE, "reply"))
    memory.append(turn(USER_ROLE, "third"))
    assert memory.history() == (
        turn(USER_ROLE, "first"),
        turn(ASSISTANT_ROLE, "reply"),
        turn(USER_ROLE, "third"),
    )


def test_history_returns_a_tuple_of_frozen_turns(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    memory.append(turn(USER_ROLE, "hi"))
    history = memory.history()
    assert isinstance(history, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        history[0].role = ASSISTANT_ROLE  # type: ignore[misc]


def test_len_counts_stored_turns(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    assert len(memory) == 0
    memory.append(turn(USER_ROLE, "a"))
    memory.append(turn(ASSISTANT_ROLE, "b"))
    assert len(memory) == 2


# --- bounded FIFO eviction ---------------------------------------------------


def test_fifo_evicts_oldest_turns_beyond_the_cap(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db", max_turns=3)
    for i in range(5):
        memory.append(turn(USER_ROLE, f"t{i}"))
    assert [t.text for t in memory.history()] == ["t2", "t3", "t4"]
    assert len(memory) == 3


def test_eviction_is_persisted_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    memory = SQLiteMemory(db, max_turns=2)
    for i in range(4):
        memory.append(turn(USER_ROLE, f"t{i}"))
    memory.close()

    reopened = SQLiteMemory(db, max_turns=2)
    assert [t.text for t in reopened.history()] == ["t2", "t3"]
    reopened.close()


def test_cap_of_one_keeps_only_the_latest_turn(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db", max_turns=1)
    memory.append(turn(USER_ROLE, "old"))
    memory.append(turn(ASSISTANT_ROLE, "new"))
    assert memory.history() == (turn(ASSISTANT_ROLE, "new"),)


def test_matches_inmemory_fifo_semantics() -> None:
    in_memory = InMemoryMemory(max_turns=3)
    on_disk = SQLiteMemory(":memory:", max_turns=3)
    for i in range(6):
        in_memory.append(turn(USER_ROLE, f"t{i}"))
        on_disk.append(turn(USER_ROLE, f"t{i}"))
    assert on_disk.history() == in_memory.history()
    in_memory.clear()
    on_disk.clear()
    assert on_disk.history() == in_memory.history() == ()
    on_disk.close()


# --- clear ---------------------------------------------------------------------


def test_clear_empties_history(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    memory.append(turn(USER_ROLE, "a"))
    memory.clear()
    assert memory.history() == ()
    assert len(memory) == 0


def test_clear_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    memory = SQLiteMemory(db)
    memory.append(turn(USER_ROLE, "a"))
    memory.clear()
    memory.close()
    assert SQLiteMemory(db).history() == ()


# --- persistence across reopen -------------------------------------------------


def test_history_survives_close_and_reopen(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    writer = SQLiteMemory(db)
    writer.append(turn(USER_ROLE, "My name is Sara"))
    writer.append(turn(ASSISTANT_ROLE, "Nice to meet you, Sara!"))
    writer.close()

    reader = SQLiteMemory(db)
    assert reader.history() == (
        turn(USER_ROLE, "My name is Sara"),
        turn(ASSISTANT_ROLE, "Nice to meet you, Sara!"),
    )
    reader.close()


def test_two_instances_share_one_database_file(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    first = SQLiteMemory(db)
    first.append(turn(USER_ROLE, "shared"))

    second = SQLiteMemory(db)
    assert second.history() == (turn(USER_ROLE, "shared"),)
    second.append(turn(ASSISTANT_ROLE, "seen"))
    assert [t.text for t in first.history()] == ["shared", "seen"]
    first.close()
    second.close()


def test_in_memory_database_works_while_open() -> None:
    memory = SQLiteMemory(":memory:")
    memory.append(turn(USER_ROLE, "volatile"))
    assert [t.text for t in memory.history()] == ["volatile"]
    memory.close()


# --- close and context manager -------------------------------------------------


def test_close_is_idempotent(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    memory.close()
    memory.close()  # must not raise


def test_operations_after_close_raise(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    memory.append(turn(USER_ROLE, "a"))
    memory.close()
    with pytest.raises(sqlite3.ProgrammingError):
        memory.append(turn(USER_ROLE, "b"))
    with pytest.raises(sqlite3.ProgrammingError):
        memory.history()
    with pytest.raises(sqlite3.ProgrammingError):
        memory.clear()


def test_context_manager_closes_on_exit(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    with SQLiteMemory(db) as memory:
        assert isinstance(memory, SQLiteMemory)
        memory.append(turn(USER_ROLE, "inside"))
        assert len(memory) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        memory.append(turn(USER_ROLE, "after"))
    assert SQLiteMemory(db).history() == (turn(USER_ROLE, "inside"),)


# --- agent and runtime wiring --------------------------------------------------


def test_agent_records_turns_into_sqlite_memory(tmp_path: Path) -> None:
    memory = SQLiteMemory(tmp_path / "m.db")
    provider = ScriptedProvider([TextResponse("answer")])
    agent = Agent(provider, memory=memory)
    result = agent.run("hello")
    assert result.success
    assert memory.history() == (
        turn(USER_ROLE, "hello"),
        turn(ASSISTANT_ROLE, "answer"),
    )
    memory.close()


def test_reopened_memory_composes_previous_transcript(tmp_path: Path) -> None:
    """A reopened file plays the role of a brand-new process remembering."""
    db = tmp_path / "m.db"

    first = Agent(
        ScriptedProvider([TextResponse("first answer")]),
        memory=SQLiteMemory(db),
    )
    assert first.run("My name is Sara").success

    second_provider = ScriptedProvider([TextResponse("second answer")])
    second = Agent(second_provider, memory=SQLiteMemory(db))
    assert second.run("What is my name?").success
    assert second_provider.calls[0][0] == EXPECTED_TRANSCRIPT


def test_runtime_factory_accepts_sqlite_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NEXUS_PROVIDER", "fake")
    memory = SQLiteMemory(tmp_path / "m.db")
    runtime = create_runtime(memory=memory)
    assert runtime.memory is memory
    assert runtime.run("hello").success
    assert runtime.memory is not None and len(runtime.memory) == 2
    memory.close()
