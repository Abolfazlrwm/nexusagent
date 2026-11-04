# Contributing to NexusAgent

Thanks for considering a contribution! This project follows a few simple
rules that keep it healthy. Please read this before opening a pull request.

## How to contribute

1. **Open an issue first** for anything bigger than a typo — describe the
   problem or the feature so we can agree on the approach before code is written.
2. **Fork the repo** and create a topic branch from `main`:
   `git checkout -b feat/my-change`
3. **Make your change** with focused commits (one logical change per commit).
4. **Add or update tests** for anything you change. A fix without a test
   that reproduces the bug will likely be asked for one.
5. **Run the checks below locally** and make sure they pass.
6. **Open a pull request** with a short description: what changed, why,
   and how you tested it.

## Project setup & checks

NexusAgent is a small, dependency-light Python package:

```bash
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

Both `ruff` and the full `pytest` suite must pass. The core is deliberately
small — if your idea needs a big new subsystem, open an issue first so we
can discuss whether it belongs here.

## Ground rules

- Keep the public behavior stable unless the issue explicitly calls for a change.
- Match the existing code style; don't mix reformatting with functional changes.
- Write commit messages in the imperative mood, e.g. `fix: handle empty payload`.
- New dependencies need a justification in the PR description.

## Reporting bugs

Use the bug report issue template and include reproduction steps, the
expected behavior, and your environment. The more reproducible the report,
the faster the fix.
