# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may break).

## [0.2.0]

### Added
- Agent loop: tool calls requested by the provider are executed and their results fed back until a final answer or `max_steps`.
- `Provider.respond(messages, tools)` structured entry point, plus `Message`, `ToolSpec`, `ToolCallRequest.call_id`.
- `OpenAIProvider` (OpenAI-compatible APIs, incl. Ollama) and `AnthropicProvider`; `ScriptedProvider` for tests and demos.
- Generic HTTP provider can return tool calls (`{"tool_name", "tool_input"}`).
- `Conversation` / `Runtime.conversation()` for multi-turn history.
- `AgentResult.steps` and `AgentResult.messages`; `AgentStep`.
- Settings: `system_prompt` (`NEXUS_SYSTEM_PROMPT`), `max_steps` (`NEXUS_MAX_STEPS`).
- CLI: `chat`, `--model`, `--max-steps`, `--system`, `-v/--verbose`; installed `nexusagent` console script.
- Strict mypy, `py.typed`, GitHub Actions CI, CONTRIBUTING.

### Changed
- `Agent.run()` now advertises registered tools to the provider. With the `http` provider, requests from `Runtime.run()` therefore include `messages` and `tools` fields in addition to `model` and `input`. `Provider.generate()` requests are unchanged.
- `NEXUS_LOG_LEVEL` is now honoured by the CLI; an invalid value is a clean error.
- A bare CLI prompt equal to `chat` now starts the chat REPL (like `tool`).
- Connection-level `OSError`s (reset, disconnect) are reported as `ProviderRequestError`.

### Fixed
- `.gitignore` now excludes caches, virtualenvs and `.env`; line endings normalized to LF (`.gitattributes`).

## [0.1.0]
- Initial runtime: `Agent`, `Provider` (fake, http), explicit `Tool` subsystem, `Runtime`, factories, CLI, configuration, logging.
