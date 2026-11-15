"""Conversation memory: context carried across runs, fully offline.

Runs the fake provider twice with one shared memory: the second prompt
carries the transcript of the first exchange, so the model sees the
conversation so far. With the fake provider the effect is visible in the
prompt itself — swap in a real provider and the model uses it as context.
"""

from nexusagent import InMemoryMemory, create_runtime

memory = InMemoryMemory()  # bounded FIFO, default max_turns=100
runtime = create_runtime(memory=memory)

first = runtime.run("Hello NexusAgent, this is our first exchange")
print(first.output)

second = runtime.run("This is the second exchange")
print(second.output)

print(f"memory now holds {len(memory)} turns (two completed exchanges)")
for turn in memory.history():
    print(f"  {turn.role}: {turn.text}")

memory.clear()
print(f"after clear(): {len(memory)} turns")
