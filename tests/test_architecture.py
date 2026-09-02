import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "nexusagent"


def get_imported_modules(path: Path) -> set[str]:
    """Return the set of dotted module names imported by a source file."""
    with open(path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    return modules


def get_source(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def assert_no_forbidden_imports(module_filename: str, forbidden: set[str]) -> None:
    path = SRC_DIR / module_filename
    imports = get_imported_modules(path)
    nexusagent_imports = {m for m in imports if m.startswith("nexusagent")}
    violations = nexusagent_imports & forbidden

    assert not violations, f"{module_filename} must not import {violations}"


# --- Rule A — core Tool abstraction ---


def test_tool_has_no_upward_dependencies():
    forbidden = {
        "nexusagent.application",
        "nexusagent.main",
        "nexusagent.runtime",
        "nexusagent.runtime_factory",
        "nexusagent.tool_factory",
        "nexusagent.tool_registry",
        "nexusagent.tool_executor",
        "nexusagent.agent",
        "nexusagent.factory",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
    }
    assert_no_forbidden_imports("tool.py", forbidden)


# --- Rule B — Tool implementations ---


def test_tool_implementations_have_no_upward_dependencies():
    forbidden = {
        "nexusagent.application",
        "nexusagent.main",
        "nexusagent.runtime",
        "nexusagent.runtime_factory",
        "nexusagent.tool_factory",
        "nexusagent.tool_registry",
        "nexusagent.tool_executor",
        "nexusagent.agent",
        "nexusagent.factory",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
    }

    for filename in ("echo_tool.py", "uppercase_tool.py", "calculator_tool.py"):
        assert_no_forbidden_imports(filename, forbidden)


# --- Rule C — Tool Registry ---


def test_tool_registry_has_no_upward_dependencies():
    forbidden = {
        "nexusagent.application",
        "nexusagent.main",
        "nexusagent.runtime",
        "nexusagent.runtime_factory",
        "nexusagent.tool_factory",
        "nexusagent.tool_executor",
        "nexusagent.agent",
        "nexusagent.factory",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
    }
    assert_no_forbidden_imports("tool_registry.py", forbidden)


# --- Rule D — Tool Factory ---


def test_tool_factory_does_not_depend_on_application_layer():
    forbidden = {
        "nexusagent.application",
        "nexusagent.main",
        "nexusagent.runtime_factory",
        "nexusagent.runtime",
        "nexusagent.agent",
        "nexusagent.factory",
        "nexusagent.provider",
        "nexusagent.providers",
        "nexusagent.http_provider",
    }
    assert_no_forbidden_imports("tool_factory.py", forbidden)


# --- Rule E — Runtime Factory ---


def test_runtime_factory_does_not_depend_on_application_layer():
    forbidden = {
        "nexusagent.application",
        "nexusagent.main",
    }
    assert_no_forbidden_imports("runtime_factory.py", forbidden)


# --- Rule F — Application layer ---


def test_application_does_not_depend_on_main():
    forbidden = {
        "nexusagent.main",
    }
    assert_no_forbidden_imports("application.py", forbidden)


# --- Rule G — Main / CLI construction boundary ---


def test_main_does_not_construct_tool_infrastructure():
    source = get_source(SRC_DIR / "main.py")

    forbidden_constructions = [
        "ToolRegistry(",
        "ToolExecutor(",
        "EchoTool(",
        "UppercaseTool(",
        "CalculatorTool(",
        "create_tool_registry(",
        "create_tool_runtime(",
        "create_runtime(",
    ]

    for construction in forbidden_constructions:
        assert construction not in source, (
            f"main.py must not directly construct via {construction!r}; "
            "it must go through nexusagent.application instead"
        )


def test_main_uses_application_layer_as_runtime_entry_point():
    imports = get_imported_modules(SRC_DIR / "main.py")

    assert "nexusagent.application" in imports


# --- Rule H — Public package API layer ---


def test_init_does_not_depend_on_main():
    forbidden = {
        "nexusagent.main",
    }
    assert_no_forbidden_imports("__init__.py", forbidden)


def test_init_does_not_construct_infrastructure():
    source = get_source(SRC_DIR / "__init__.py")

    forbidden_constructions = [
        "ToolRegistry(",
        "ToolExecutor(",
        "EchoTool(",
        "UppercaseTool(",
        "CalculatorTool(",
        "create_tool_registry(",
        "create_tool_runtime(",
        "create_runtime(",
        "create_application_runtime(",
    ]

    for construction in forbidden_constructions:
        assert construction not in source, (
            f"__init__.py must not directly construct via {construction!r}; "
            "it must only re-export public objects"
        )


def test_init_exposes_agent_result():
    source = get_source(SRC_DIR / "__init__.py")

    assert "AgentResult" in source, "__init__.py must continue to export AgentResult"
