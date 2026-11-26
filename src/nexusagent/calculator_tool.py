"""The built-in calculator tool.

Evaluates arithmetic expressions with the usual operator precedence
(``*``/``/`` bind tighter than ``+``/``-``, all left-associative) over a
safe hand-written tokenizer and parser — no ``eval``, no ``exec``, no
imports beyond :mod:`re`. Since v1.9.1 the tool accepts full chains
(``2 + 3 * 4``), not just single binary operations, so the demo brain
can route natural arithmetic straight through the tool loop.
"""

from __future__ import annotations

import math
import re

from nexusagent.tool import Tool

_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_OPERATORS = frozenset("+-*/")

_INVALID_MESSAGE = "Invalid expression: expected numbers joined by + - * / (e.g. 2 + 3 * 4)"


def _tokenize(text: str) -> list[str]:
    """Split the input into number and operator tokens, left to right."""
    tokens: list[str] = []
    position = 0
    length = len(text)
    while position < length:
        char = text[position]
        if char.isspace():
            position += 1
            continue
        if char in _OPERATORS:
            tokens.append(char)
            position += 1
            continue
        match = _NUMBER_PATTERN.match(text, position)
        if match:
            tokens.append(match.group(0))
            position = match.end()
            continue
        raise ValueError(_INVALID_MESSAGE)
    return tokens


def _apply(operator: str, left: float, right: float) -> float:
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if right == 0:
        raise ZeroDivisionError("Division by zero")
    return left / right


def _evaluate(tokens: list[str]) -> float:
    """Precedence-climbing evaluation over the token list.

    Grammar: ``expr := term (('+'|'-') term)*``, ``term := unary
    (('*'|'/') unary)*``, ``unary := ('-'|'+') unary | number``. Every
    malformed shape raises ``ValueError`` with the same safe message.
    """
    total = len(tokens)

    def parse_expr(pos: int) -> tuple[float, int]:
        value, pos = parse_term(pos)
        while pos < total and tokens[pos] in ("+", "-"):
            operator = tokens[pos]
            right, pos = parse_term(pos + 1)
            value = _apply(operator, value, right)
        return value, pos

    def parse_term(pos: int) -> tuple[float, int]:
        value, pos = parse_unary(pos)
        while pos < total and tokens[pos] in ("*", "/"):
            operator = tokens[pos]
            right, pos = parse_unary(pos + 1)
            value = _apply(operator, value, right)
        return value, pos

    def parse_unary(pos: int) -> tuple[float, int]:
        if pos >= total:
            raise ValueError(_INVALID_MESSAGE)
        token = tokens[pos]
        if token == "-":
            value, pos = parse_unary(pos + 1)
            return -value, pos
        if token == "+":
            return parse_unary(pos + 1)
        try:
            return float(token), pos + 1
        except ValueError as exc:
            raise ValueError(_INVALID_MESSAGE) from exc

    value, pos = parse_expr(0)
    if pos != total:
        raise ValueError(_INVALID_MESSAGE)
    return value


class CalculatorTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="calculator", description="Performs basic arithmetic operations.")

    def execute(self, input_data: str) -> str:
        if not input_data.strip():
            raise ValueError(_INVALID_MESSAGE)
        tokens = _tokenize(input_data)
        if len(tokens) < 3:
            # A lone number (or an operator without operands) is not an expression.
            raise ValueError(_INVALID_MESSAGE)
        result = _evaluate(tokens)
        if not math.isfinite(result):
            raise ValueError(_INVALID_MESSAGE)
        return _format_result(result)


def _format_result(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)
