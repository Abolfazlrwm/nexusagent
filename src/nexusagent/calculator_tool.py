from __future__ import annotations

import re

from nexusagent.tool import Tool

_EXPRESSION_PATTERN = re.compile(r"\s*(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)\s*")


class CalculatorTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="calculator", description="Performs basic arithmetic operations.")

    def execute(self, input_data: str) -> str:
        match = _EXPRESSION_PATTERN.fullmatch(input_data)
        if not match:
            raise ValueError(
                "Invalid expression: expected 'number operator number' with operator one of + - * /"
            )

        left = float(match.group(1))
        operator = match.group(2)
        right = float(match.group(3))

        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        else:
            if right == 0:
                raise ZeroDivisionError("Division by zero is not allowed")
            result = left / right

        return _format_result(result)


def _format_result(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)
