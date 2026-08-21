import argparse

from nexusagent import create_runtime


def main() -> None:
    parser = argparse.ArgumentParser(prog="nexusagent")
    parser.add_argument("input_text", help="input text to run through the agent")
    args = parser.parse_args()

    runtime = create_runtime()
    result = runtime.run(args.input_text)
    print(result.output)
