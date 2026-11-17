"""Persistent conversation memory with SQLite, fully offline.

SQLiteMemory stores completed exchanges in a local SQLite database file,
so history survives process restarts. This example runs twice with a
reopened memory to simulate two separate processes: the second run reads
what the first one wrote and composes it into its prompt. With the fake
provider the effect is visible in the prompt itself — swap in a real
provider and the model uses it as context.
"""

import tempfile
from pathlib import Path

from nexusagent import SQLiteMemory, create_runtime

db_path = Path(tempfile.gettempdir()) / "nexusagent-example-memory.db"

# "Process one": record an exchange.
memory = SQLiteMemory(db_path, max_turns=20)
runtime = create_runtime(memory=memory)
first = runtime.run("Hello NexusAgent, this is our first exchange")
print(first.output)
memory.close()

# "Process two": reopen the same file — the history is still there.
memory = SQLiteMemory(db_path, max_turns=20)
runtime = create_runtime(memory=memory)
second = runtime.run("This is the second exchange")
print(second.output)

print(f"memory now holds {len(memory)} turns (two completed exchanges)")
for turn in memory.history():
    print(f"  {turn.role}: {turn.text}")

memory.clear()  # delete the database rows, start fresh
memory.close()
print(f"after clear(): 0 turns — but the file {db_path} still exists")
