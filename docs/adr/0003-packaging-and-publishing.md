# ADR 0003: Publish as `nexusagent` with Trusted Publishing and a Single-Sourced Version

- Status: Accepted — **amended by [ADR 0004](0004-pypi-distribution-name.md)**:
  the distribution name was changed to `nexusagent-runtime` before the first
  PyPI upload; everything else in this ADR stands.
- Date: 2026-11-09
- Deciders: Abolfazl Ranjbaran

## Context

The project accumulated Git tags (v0.1.0–v0.3.0) and GitHub releases without
ever being published to PyPI. Three packaging problems had to be resolved
before a first publish:

1. **Name.** `nexusagent` was free on PyPI (checked 2026-11-09); the hyphenated
   `nexus-agent` is taken. Alternatives like `nexusagent-core` fragment the
   brand for no benefit while the primary name is available.
2. **Version truth.** `pyproject.toml` and `nexusagent.__version__` said
   `0.1.0` while tags reached `v0.3.0`. Publishing with a version that
   contradicts the repository's own release history is unacceptable.
3. **Publishing credentials.** Long-lived PyPI API tokens stored in CI
   secrets are a standing risk.

## Decision

- **Publish as `nexusagent`.** First PyPI release is **0.4.0** — continuing
  the existing tag sequence, not restarting at 0.1.0.
- **Version is single-sourced** from `nexusagent.__version__` via
  `setuptools`' `attr:` directive. `pyproject.toml` declares
  `dynamic = ["version"]`; there is exactly one place to bump a version,
  and `tests/test_init.py` asserts it matches the installed distribution
  metadata.
- **Publishing uses Trusted Publishing (OIDC)**: `.github/workflows/publish.yml`
  runs on `v*` tags (and `workflow_dispatch`), builds sdist+wheel, checks
  metadata with `twine`, and uploads from a job using the `pypi`
  environment with `id-token: write`. No PyPI token is stored anywhere.
- **1.0.0 is deferred** until the public API has survived a PyPI release
  cycle and the tool-loop/vendor-adapter story has settled. Honesty about
  pre-1.0 status ("Development Status :: 4 - Beta") is preferred over a
  premature 1.0.

## Consequences

- Releasing means: bump `nexusagent.__version__`, date the CHANGELOG entry,
  tag `vX.Y.Z`, create the GitHub Release from the CHANGELOG — CI does the
  rest.
- One-time manual setup on pypi.org (register the Trusted Publisher) is
  required; the publish job fails with an OIDC error until then — by design,
  fail-closed.
- The package now ships `py.typed`, a `nexusagent` console script, and full
  `[project.urls]`/classifiers metadata; packaging metadata is part of the
  public contract and changes to it should be noted in the CHANGELOG.
