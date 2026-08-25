import argparse
import sys
from dataclasses import replace

from nexusagent import create_runtime
from nexusagent.config import Settings
from nexusagent.provider import ProviderError


def main() -> None:
    parser = argparse.ArgumentParser(prog="nexusagent")
    parser.add_argument("input_text", help="input text to run through the agent")
    parser.add_argument("--provider", help="provider to use (overrides NEXUS_PROVIDER)")
    args = parser.parse_args()

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
