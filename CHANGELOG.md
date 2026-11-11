# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-11-11

### Added

- **OpenAI-compatible provider** (`NEXUS_PROVIDER=openai`,
  `create_provider("openai", config)`) speaking the Chat Completions wire
  format. Works with OpenAI itself and with any compatible server — Ollama,
  LM Studio, vLLM, OpenRouter, Groq — via a `NEXUS_ENDPOINT` override
  (see [ADR 0005](docs/adr/0005-openai-compatible-provider.md)):
  - Stateless loop rehydration: prompt + accumulated tool results are mapped
    to `user` / assistant `tool_calls` / `tool` messages with synthesized
    call ids; no state survives between iterations.
  - Full tool calling: tools are advertised as functions with a single
    required `input` string parameter; models that pick their own single
    parameter name are accepted. Failed tool results are fed back with an
    `Error: ` prefix.
  - Configuration: `model` required, `endpoint` optional (defaults to the
    official API), `api_key` optional (local servers need none) — still
    zero runtime dependencies, no vendor SDK.
- Shared HTTP transport `nexusagent.http_provider.post_json()` used by both
  HTTP-based providers; timeout handling, error mapping and key-safety are
  defined in one place.
- Architecture rule N (no upward dependencies for `openai_provider.py`),
  enforced by tests like the other layer rules.

### Changed

- Endpoint scheme validation (`http`/`https` only) now applies to any
  provider that sets an endpoint, not only `http`.
- 88 new contract tests: the suite grows from 628 to 716 tests; coverage
  rises from 99.05% to 99.21% (`openai_provider.py` itself: 100%).

## [0.4.0] - 2026-11-09

First release published to PyPI as [`nexusagent-runtime`](https://pypi.org/project/nexusagent-runtime/).
The **import name** remains `nexusagent`.

### Added

- `py.typed` marker: the package now ships full type information for mypy/IDE users.
- `nexusagent` console command (previously only `python -m nexusagent` was available).
- **Autonomous tool loop**: `Provider.generate_response()` may answer with a
  `ToolCallRequest`; the Agent runs the requested tool, feeds the `ToolResult`
  back, and repeats until a text answer or `max_iterations` (default 10).
  Text-only providers keep working unchanged through the default
  implementation. The vendor-neutral HTTP wire format is documented in
  `docs/protocol.md` (ADR 0002). Includes the deterministic, network-free
  `ScriptedProvider` for demos and tests.
- Project documentation under `docs/`: architecture overview, concepts,
  custom provider/tool guides, the HTTP protocol spec, and ADRs 0001–0004.
- Executable examples under `examples/` (basic runtime, custom tool, tool loop
  demo — all runnable offline, no API keys).
- CI: lint + format (ruff), `mypy --strict`, tests with an enforced coverage
  floor (≥95%) on Python 3.10–3.13, wheel build with a clean-venv smoke test,
  and a self-hosted coverage badge.
- PyPI publishing workflow using Trusted Publishing (OIDC), triggered on `v*` tags.
- `SECURITY.md`, this `CHANGELOG.md`, `.pre-commit-config.yaml`, and an expanded
  `CONTRIBUTING.md`.

### Changed

- Version is single-sourced from `nexusagent.__version__` (it previously
  drifted: `pyproject.toml` said 0.1.0 while repository tags reached v0.3.0).
- Packaging metadata modernized: PEP 639 SPDX license, classifiers,
  `[project.urls]`, package keywords.
- Lint rules extended (bugbear, comprehensions, pyupgrade, simplify, etc.) and
  the whole codebase brought up to them.
- **Distribution name is `nexusagent-runtime`** (originally planned as
  `nexusagent`). PyPI's confusingly-similar-name rule blocks registering
  `nexusagent` because an unrelated placeholder package, `nexus-agent`,
  already exists. The `v0.4.0` tag was moved to the renamed commit before the
  first PyPI upload — nothing was ever published under the old name, so no
  user is affected. See [ADR 0004](docs/adr/0004-pypi-distribution-name.md).

### Fixed

- `NEXUS_TIMEOUT` with a non-numeric value now raises a readable
  `ValueError` ("Invalid NEXUS_TIMEOUT: 'abc' …") instead of a raw
  float-conversion traceback.
- `HttpProvider` HTTP errors now include a short snippet of the response body
  when the backend provides one (rate limits, auth failures), truncated to
  200 characters.
- `ToolExecutionError` messages now preserve the original error class name
  (e.g. `ZeroDivisionError: …`); the exception itself remains available as
  `__cause__`.

## [0.3.0] - 2026-10-12

### Added

- Tool availability checks: `Agent.has_tool()` and `ToolRegistry.has()`.
- Structured provider response groundwork (`TextResponse`, `ToolCallRequest`,
  `ProviderResponse`) with contract tests — not yet produced by any Provider.
- Explicit architecture tests that forbid lower layers importing upward.

### Changed

- Provider factories hardened: unsupported provider names raise
  `ProviderConfigurationError`; `Runtime`/`Settings` construction validated
  before any provider is built.

## [0.2.0] - 2026-09-20

### Added

- CLI tool commands: `python -m nexusagent tool list` and
  `python -m nexusagent tool run <name> <input>`.
- `HttpProvider`: generic HTTP backend sending `{"model", "input"}` and
  reading `{"output"}`, with `NEXUS_PROVIDER` / `NEXUS_ENDPOINT` /
  `NEXUS_API_KEY` / `NEXUS_TIMEOUT` configuration.

### Changed

- `Settings` gained `provider`, `endpoint`, `timeout` fields with local
  validation (no network access during validation).

## [0.1.0] - 2026-08-25

### Added

- Initial foundation: `Provider`/`FakeProvider`, `Agent`/`AgentResult`,
  `Tool`/`ToolRegistry`/`ToolExecutor`, `Runtime`, built-in tools
  (`echo`, `uppercase`, `calculator`), `Settings` from `NEXUS_*` environment
  variables, and the factory layer (`create_runtime`,
  `create_application_runtime`).

[Unreleased]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Abolfazlrwm/nexusagent/releases/tag/v0.1.0
