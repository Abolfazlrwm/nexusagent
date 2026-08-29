import pytest

from nexusagent.calculator_tool import CalculatorTool
from nexusagent.tool import Tool


def test_calculator_tool_is_a_tool():
    tool = CalculatorTool()

    assert isinstance(tool, Tool)


def test_calculator_tool_has_stable_name():
    tool = CalculatorTool()

    assert tool.name == "calculator"


def test_calculator_tool_has_description():
    tool = CalculatorTool()

    assert tool.description == "Performs basic arithmetic operations."


# --- Addition ---


def test_addition():
    tool = CalculatorTool()

    assert tool.execute("2 + 3") == "5"


# --- Subtraction ---


def test_subtraction():
    tool = CalculatorTool()

    assert tool.execute("10 - 4") == "6"


# --- Multiplication ---


def test_multiplication():
    tool = CalculatorTool()

    assert tool.execute("6 * 7") == "42"


# --- Division ---


def test_division_evenly():
    tool = CalculatorTool()

    assert tool.execute("20 / 5") == "4"


def test_division_fractional_result():
    tool = CalculatorTool()

    assert tool.execute("10 / 4") == "2.5"


# --- Decimal operands ---


def test_decimal_operands():
    tool = CalculatorTool()

    assert tool.execute("2.5 + 1.5") == "4"


# --- Negative numbers ---


def test_negative_left_operand():
    tool = CalculatorTool()

    assert tool.execute("-5 + 2") == "-3"


def test_negative_result():
    tool = CalculatorTool()

    assert tool.execute("2 - 10") == "-8"


# --- Whitespace ---


@pytest.mark.parametrize(
    "expression",
    ["2+3", "2 + 3", "  2 + 3", "2   +   3", "2 + 3  "],
)
def test_whitespace_variants_all_produce_five(expression):
    tool = CalculatorTool()

    assert tool.execute(expression) == "5"


# --- Invalid expressions ---


@pytest.mark.parametrize(
    "expression",
    [
        "hello",
        "2",
        "2 + 3 + 4",
        "2 **",
        "2 ^ 3",
        "2 + abc",
        "/ 2",
        "2 /",
        "",
        "   +",
    ],
)
def test_invalid_expressions_are_rejected(expression):
    tool = CalculatorTool()

    with pytest.raises(ValueError):
        tool.execute(expression)


# --- Division by zero ---


def test_division_by_zero_fails_cleanly():
    tool = CalculatorTool()

    with pytest.raises(ZeroDivisionError):
        tool.execute("10 / 0")


# --- Security ---


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "eval('1+1')",
        "exec('1+1')",
        "os.system('ls')",
        "2 ** 10",
        "(2 + 3)",
        "2 + 3 * 4",
    ],
)
def test_dangerous_expressions_are_rejected_not_evaluated(expression):
    tool = CalculatorTool()

    with pytest.raises(ValueError):
        tool.execute(expression)


def test_calculator_tool_source_does_not_use_eval_or_exec():
    import inspect

    source = inspect.getsource(CalculatorTool)

    assert "eval(" not in source
    assert "exec(" not in source


# --- Statelessness ---


def test_two_executions_are_independent():
    tool = CalculatorTool()

    result1 = tool.execute("2 + 3")
    result2 = tool.execute("10 - 4")

    assert result1 == "5"
    assert result2 == "6"


# --- No external side effects ---


def test_calculator_tool_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("CalculatorTool must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    tool = CalculatorTool()
    tool.execute("2 + 3")


def test_calculator_tool_does_not_access_filesystem(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("CalculatorTool must not access the filesystem")

    monkeypatch.setattr("builtins.open", fail_if_called)

    tool = CalculatorTool()
    tool.execute("2 + 3")


def test_calculator_tool_works_without_any_nexus_environment_variables(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("NEXUS_"):
            monkeypatch.delenv(key, raising=False)

    tool = CalculatorTool()

    assert tool.execute("2 + 3") == "5"
