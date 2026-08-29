import argparse
import sys
from dataclasses import replace

from nexusagent import create_runtime
from nexusagent.config import Settings
from nexusagent.echo_tool import EchoTool
from nexusagent.provider import ProviderError
from nexusagent.tool_executor import ToolExecutionError, ToolExecutor
from nexusagent.tool_registry import ToolRegistry
from nexusagent.uppercase_tool import UppercaseTool


def _build_tool_runtime():
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(UppercaseTool())
    executor = ToolExecutor()
    return create_runtime(tool_registry=registry, tool_executor=executor)


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


def main() -> None:
    argv = sys.argv[1:]

    if argv and argv[0] == "tool":
        _run_tool_command(argv[1:])
        return

    parser = argparse.ArgumentParser(prog="nexusagent")
    parser.add_argument("input_text", help="input text to run through the agent")
    parser.add_argument("--provider", help="provider to use (overrides NEXUS_PROVIDER)")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.provider is not None:
        settings = replace(settings, provider=args.provider)

    try:
        runtime = create_runtime(settings)
    except (ValueError, ProviderError) as exc:
        print(f"nexusagent: error: {exc}", file=sys.stderr)
        sys.exit(1)

    result = runtime.run(args.input_text)
    if not result.success:
        print(f"nexusagent: error: {result.output}", file=sys.stderr)
        sys.exit(1)

    print(result.output)
