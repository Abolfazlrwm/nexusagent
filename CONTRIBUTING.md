# Contributing to NexusAgent

Thanks for considering a contribution! This project follows a few simple
rules that keep it healthy. Please read this before opening a pull request.

## How to contribute

1. **Open an issue first** for anything bigger than a typo — describe the
   problem or the feature so we can agree on the approach before code is written.
2. **Fork the repo** and create a topic branch from `main`:
   `git checkout -b feat/my-change`
3. **Make your change** with focused commits (one logical change per commit),
   using [Conventional Commits](https://www.conventionalcommits.org/):
   `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`, `refactor:`.
4. **Add or update tests** for anything you change. A fix without a test
   that reproduces the bug will likely be asked for one.
5. **Run the checks below locally** and make sure they pass.
6. **Open a pull request** with a short description: what changed, why,
   and how you tested it. CI must be green before merge.

## Project setup & checks

NexusAgent is a small, **zero-runtime-dependency** Python package:

```bash
pip install -e ".[dev]"
python scripts/check.py   # ruff check + ruff format --check + mypy --strict + pytest
```

Individual checks:

```bash
ruff check src tests          # lint
ruff format --check src tests # formatting
mypy                          # strict type check (src/ only)
pytest -q                     # tests with a coverage report
```

The test suite enforces a **coverage floor of 95%** (configured in
`pyproject.toml`). All of this also runs in CI on Python 3.10–3.13, plus a
wheel build with a clean-venv smoke test.

Optional: install the [pre-commit](https://pre-commit.com/) hooks to run the
same checks automatically on every commit:

```bash
pre-commit install
```

## Ground rules

- Keep the public behavior stable unless the issue explicitly calls for a change.
  **Breaking changes to the public API require an ADR** (see below) and explicit
  agreement in the issue/PR.
- Match the existing code style; don't mix reformatting with functional changes.
- The core is deliberately small — if your idea needs a big new subsystem, open
  an issue first so we can discuss whether it belongs here.
- New runtime dependencies are effectively frozen: the core is stdlib-only by
  design (see `docs/adr/`). Dev dependencies are fine with justification.
- Be honest in docs and README: limitations are documented, not hidden.

## Architecture decision records

Significant decisions (public API shape, new abstractions, protocol formats,
packaging/publishing policy) get a short ADR under `docs/adr/` following the
existing numbering. If your PR changes something a newcomer would later ask
"why is it this way?", it probably deserves one.

## Reporting bugs

Use the bug report issue template and include reproduction steps, the
expected behavior, and your environment. The more reproducible the report,
the faster the fix.

## Security issues

Please do **not** open public issues for security problems — see
[SECURITY.md](SECURITY.md) for the private reporting path.
