from nexusagent.runtime import create_runtime

runtime = create_runtime()
result = runtime.run("Hello NexusAgent")
print(result.output)
