import argparse
import sys
from dataclasses import replace

import nexusagent
from nexusagent.application import Runtime, create_application_runtime
from nexusagent.chat import build_chat_runtime, run_chat_repl
from nexusagent.config import Settings
from nexusagent.provider import ProviderConfigurationError, ProviderError
from nexusagent.tool_executor import ToolExecutionError


def _build_tool_runtime() -> Runtime:
    return create_application_runtime()


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
        print(f"nexusagent: error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(result)


def _run_chat_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="nexusagent chat",
        description="Chat with the NexusAgent runtime in your terminal (ADR 0018).",
    )
    parser.add_argument(
        "--provider",
        help="provider to use (default: the offline demo brain; overrides NEXUS_PROVIDER)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="print whole answers instead of streaming word by word",
    )
    args = parser.parse_args(argv)

    try:
        runtime, label = build_chat_runtime(args.provider)
    except (ValueError, ProviderConfigurationError) as exc:
        print(f"nexusagent: error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        run_chat_repl(runtime, label=label, stream=not args.no_stream)
    except (ProviderError, ToolExecutionError) as exc:
        print(f"nexusagent: error: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] == "tool":
        _run_tool_command(argv[1:])
        return

    if argv and argv[0] == "chat":
        _run_chat_command(argv[1:])
        return

    parser = argparse.ArgumentParser(
        prog="nexusagent",
        description="Run a prompt through the NexusAgent runtime.",
    )
    parser.add_argument(
        "input_text",
        nargs="?",
        help="input text to run through the agent",
    )
    parser.add_argument("--provider", help="provider to use (overrides NEXUS_PROVIDER)")
    parser.add_argument(
        "--stream",
        action="store_true",
        help="print provider text as it is generated (streaming backends only)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed version and exit",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(f"nexusagent {nexusagent.__version__}")
        return

    if args.input_text is None:
        parser.error("the following arguments are required: input_text")

    settings = Settings.from_env()
    if args.provider is not None:
        settings = replace(settings, provider=args.provider)

    try:
        runtime = create_application_runtime(settings)
    except (ValueError, ProviderError) as exc:
        print(f"nexusagent: error: {exc}", file=sys.stderr)
        sys.exit(1)

    printed_delta = False

    def _print_delta(delta: str) -> None:
        nonlocal printed_delta
        printed_delta = True
        print(delta, end="", flush=True)

    result = runtime.run(args.input_text, on_delta=_print_delta if args.stream else None)

    if not result.success:
        print(f"nexusagent: error: {result.output}", file=sys.stderr)
        sys.exit(1)

    if args.stream and printed_delta:
        # The answer was already printed fragment by fragment; close the line.
        print()
    else:
        print(result.output)
