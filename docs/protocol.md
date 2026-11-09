# NexusAgent HTTP Protocol

The `http` provider talks to any backend that implements this small JSON
protocol. It is vendor-neutral: an adapter in front of OpenAI, Anthropic, a
local model, or a test double can all speak it.

## Request

`POST <NEXUS_ENDPOINT>` with `Content-Type: application/json` (plus
`Authorization: Bearer <NEXUS_API_KEY>` if a key is set).

```json
{
  "model": "my-model",
  "input": "What is 19 + 23?",
  "tools": [
    {"name": "calculator", "description": "Performs basic arithmetic operations."}
  ],
  "tool_results": [
    {"tool_name": "calculator", "tool_input": "19 + 23", "output": "42", "is_error": false}
  ]
}
```

| Field          | Always sent | Meaning                                                                 |
| -------------- | ----------- | ----------------------------------------------------------------------- |
| `model`        | yes         | The configured model identifier (may be `null`).                        |
| `input`        | yes         | The user's original prompt. It is the same on every request in a run.   |
| `tools`        | no          | Tools the agent can run for you. Omitted when the agent has none.       |
| `tool_results` | no          | Results of tool calls you already requested in this run, oldest first. Omitted on the first request. |

`is_error: true` means the tool failed (unknown tool, bad input, tool crash);
`output` then contains the error message so the model can retry or explain.

## Response

A JSON object that is **exactly one** of:

```json
{"output": "The answer is 42."}
```

a final text answer, which ends the run; or

```json
{"tool_name": "calculator", "tool_input": "19 + 23"}
```

a request for the agent to run a tool and call you again with the result.

Anything else is rejected with a `ProviderResponseError`: non-JSON, a non-object,
both `output` and `tool_name`, neither, an empty `output`, or a missing/non-string
`tool_name` / `tool_input`.

## The loop

```text
Agent.run(prompt)
  └─ repeat, at most max_iterations times (default 10):
       response = provider(prompt, tools, tool_results so far)
       ├─ text          -> return AgentResult(output=text, success=True)
       └─ tool request  -> run the tool, append a ToolResult, continue
  exceeded the limit    -> AgentResult(success=False)
```

Tool failures never crash the run: they are fed back with `is_error: true`.
A provider or protocol failure ends the run with `success=False` and a
`provider error: ...` message.
