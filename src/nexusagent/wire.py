"""Helpers shared by providers that talk to function-calling LLM APIs.

NexusAgent tools take and return a single string, so every tool is advertised
to the model as a function with one required string parameter named ``input``.
"""

from __future__ import annotations

from typing import Any

from nexusagent.provider import ProviderResponseError

TOOL_INPUT_KEY = "input"


def tool_parameters_schema(description: str) -> dict[str, Any]:
    """JSON Schema for the arguments of one NexusAgent tool."""
    return {
        "type": "object",
        "properties": {TOOL_INPUT_KEY: {"type": "string", "description": description}},
        "required": [TOOL_INPUT_KEY],
    }


def extract_tool_input(arguments: object) -> str:
    """Pull the tool's string input out of a model-produced arguments object."""
    if not isinstance(arguments, dict):
        raise ProviderResponseError("tool call arguments must be a JSON object")

    value = arguments.get(TOOL_INPUT_KEY)
    if value is None and len(arguments) == 1:
        # Be lenient with models that pick their own parameter name.
        value = next(iter(arguments.values()))

    if not isinstance(value, str):
        raise ProviderResponseError(f"tool call arguments must contain a string {TOOL_INPUT_KEY!r}")

    return value
