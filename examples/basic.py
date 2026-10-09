"""Smallest possible usage: the offline fake provider, no configuration needed."""

from nexusagent import create_application_runtime

runtime = create_application_runtime()
result = runtime.run("Hello NexusAgent")
print(result.output)
