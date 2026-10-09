# Contributing

```bash
git clone https://github.com/Abolfazlrwm/nexusagent && cd nexusagent
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/check.py
```

`scripts/check.py` runs `ruff check`, `ruff format --check`, `mypy` (strict) and `pytest`; CI runs the same.

## Ground rules

- **Standard library only** at runtime. A test fails if a third-party import appears in `src/`.
- **Respect the layering** tested in `tests/test_architecture.py` (e.g. `agent` never imports a concrete provider; `main` goes through `application`). If a rule must change, change the test in the same PR and say why.
- **Providers**: implement `generate()` (and `respond()` for tool calling); register in `factory.py`; add to `Settings` validation. Tests must not touch the network — mock `urlopen` or use `ScriptedProvider`.
- **Never leak secrets**: error messages and `repr`s must not contain API keys.
- Small, focused PRs with tests. Update `CHANGELOG.md`.

## Release checklist

1. Update version in `pyproject.toml` and `src/nexusagent/__init__.py` (and `tests/test_init.py`).
2. Move the Unreleased notes in `CHANGELOG.md` under the new version.
3. `python scripts/check.py`, then `git tag vX.Y.Z && git push --tags`.
