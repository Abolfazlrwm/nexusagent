import argparse
import sys
from dataclasses import replace
from typing import Any, NoReturn

from nexusagent.application import create_application_runtime
from nexusagent.config import Settings
from nexusagent.logging import configure_logging
from nexusagent.provider import ProviderError
from nexusagent.tool_executor import ToolExecutionError

_CHAT_HELP = "commands: /reset clears the conversation, /exit (or Ctrl-D) quits"


def _build_tool_runtime() -> Any:
    return create_application_runtime()


def _fail(message: str) -> NoReturn:
    print(f"nexusagent: error: {message}", file=sys.stderr)
    sys.exit(1)


def _run_tool_list_command() -> None:
    runtime = _build_tool_runtime()
    for tool in runtime.list_tools():
        print(f"{tool.name} - {tool.description}")


def _run_tool_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="nexusagent tool")
    subparsers = parser.add_subparsers(dest="tool_command", required=True)

    run_parser = subparsers.add_parser("run", help="run a registered tool")
    run_parser.add_argument("tool_name", help="name of the tool to run")
    run_parser.add_argument("input_data", help="input passed to the tool")

    subparsers.add_parser("list", help="list registered tools")

    args = parser.parse_args(argv)

    if args.tool_command == "list":
        _run_tool_list_command()
        return

    runtime = _build_tool_runtime()

    try:
        result = runtime.execute_tool(args.tool_name, args.input_data)
    except (KeyError, TypeError, ValueError, ToolExecutionError, RuntimeError) as exc:
        _fail(str(exc))

    print(result)


def _add_agent_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", help="provider to use (overrides NEXUS_PROVIDER)")
    parser.add_argument("--model", help="model name (overrides NEXUS_MODEL)")
    parser.add_argument(
        "--max-steps",
        type=int,
        help="maximum model/tool round-trips per run (overrides NEXUS_MAX_STEPS)",
    )
    parser.add_argument("--system", help="system prompt (overrides NEXUS_SYSTEM_PROMPT)")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log tool calls and debug output to stderr"
    )


def _build_runtime(args: argparse.Namespace) -> Any:
    """Build a Runtime from env settings + CLI overrides; exit cleanly on bad config."""
    settings = Settings.from_env()
    overrides = {
        "provider": args.provider,
        "model": args.model,
        "max_steps": args.max_steps,
        "system_prompt": args.system,
    }
    settings = replace(settings, **{k: v for k, v in overrides.items() if v is not None})

    try:
        configure_logging("DEBUG" if args.verbose else settings.log_level)
        return create_application_runtime(settings)
    except (ValueError, ProviderError) as exc:
        _fail(str(exc))


def _run_chat_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="nexusagent chat", description=_CHAT_HELP)
    _add_agent_options(parser)
    args = parser.parse_args(argv)

    conversation = _build_runtime(args).conversation()
    print(f"NexusAgent chat ({_CHAT_HELP})", file=sys.stderr)

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not line:
            continue

        if line in ("/exit", "/quit"):
            return

        if line == "/reset":
            conversation.reset()
            print("(conversation cleared)", file=sys.stderr)
            continue

        result = conversation.send(line)
        if result.success:
            print(result.output)
        else:
            print(f"nexusagent: error: {result.output}", file=sys.stderr)


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] == "tool":
        _run_tool_command(argv[1:])
        return

    if argv and argv[0] == "chat":
        _run_chat_command(argv[1:])
        return

    parser = argparse.ArgumentParser(prog="nexusagent")
    parser.add_argument("input_text", help="input text to run through the agent")
    _add_agent_options(parser)
    args = parser.parse_args(argv)

    runtime = _build_runtime(args)

    result = runtime.run(args.input_text)
    if not result.success:
        _fail(result.output)

    print(result.output)
