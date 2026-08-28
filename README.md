# NexusAgent

NexusAgent is an experimental, modular AI agent runtime being developed incrementally. It aims to eventually support planning, tool execution, memory, retrieval, and evaluation — but is currently just getting started.

## Status

This project is currently in the initial foundation stage. No agent functionality has been implemented yet.

## Roadmap

Future versions may introduce:

- Agent Core
- Tool System
- Memory
- RAG
- Evaluation
- API

None of these features exist yet.

## Providers

NexusAgent selects a provider via `NEXUS_PROVIDER` (or `--provider` on the CLI). Two providers exist today:

- `fake` (default) — deterministic, no network access.
- `http` — a generic HTTP provider. It sends `{"model": ..., "input": ...}` as a JSON POST to a configured endpoint and expects a JSON response with an `"output"` field. It is not tied to any specific vendor.

Relevant environment variables:

- `NEXUS_PROVIDER` — provider name (`fake` or `http`)
- `NEXUS_MODEL` — model identifier passed to the provider
- `NEXUS_API_KEY` — sent as a `Bearer` token if set
- `NEXUS_ENDPOINT` — HTTP provider endpoint URL
- `NEXUS_TIMEOUT` — HTTP request timeout in seconds (default `30`)

The `http` provider only performs a network request when it actually runs — selecting it does not make any request on its own.

## Tools

A registered tool can be run directly from the CLI:

```bash
python -m nexusagent tool run echo "hello world"
```

```text
hello world
```

Currently the built-in `echo` tool is available, which returns its input unchanged.

## Development

NexusAgent is being developed incrementally, through small, focused changes.

Run all local quality checks (lint, format check, tests) with:

```bash
python scripts/check.py
```
