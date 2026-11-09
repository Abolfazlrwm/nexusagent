# ADR 0004: PyPI distribution name is `nexusagent-runtime`

- Status: Accepted
- Date: 2026-11-09
- Deciders: Abolfazl Ranjbaran
- Amends: [ADR 0003](0003-packaging-and-publishing.md)

## Context

ADR 0003 decided to publish this project on PyPI as `nexusagent`, based on a
JSON-API check that showed the exact name was unregistered.

When the GitHub Trusted Publisher was registered on pypi.org, PyPI rejected
the name:

> This project name is too similar to an existing project

PyPI treats names as the same when they differ only by `-`, `_` and `.`
separators. An unrelated placeholder package [`nexus-agent`](https://pypi.org/project/nexus-agent/)
(v0.0.1, "Nexus Agent placeholder package", one release, uploaded
2025-11-26, no homepage, no repository) already occupies that identity, so
`nexusagent` cannot be registered — by anyone, regardless of the placeholder's
activity.

The first release (v0.4.0) had not been uploaded when this was discovered, so
the name could still be changed at zero user-facing cost.

## Decision

- **Publish on PyPI as `nexusagent-runtime`.** The name was verified
  unregistered on 2026-11-09 and does not collide with any existing project
  under PyPI's separator-insensitive similarity rule.
- **The import name stays `nexusagent`.** Installed code, `import nexusagent`,
  the `nexusagent` console script, `NEXUS_*` environment variables and the
  repository name (`github.com/Abolfazlrwm/nexusagent`) are all unchanged.
  Only the *distribution* (install) name changes: `pip install
  nexusagent-runtime`.
- The v0.4.0 tag was moved to the commit that renames the distribution.
  Nothing had been published under either name, so re-tagging affects no
  downstream users.

## Alternatives considered

- **Ask PyPI support to transfer/block the placeholder** (`nexus-agent` is an
  empty placeholder with no releases of substance). Possible in principle,
  but slow, uncertain, and it would block the first release indefinitely.
  The project can revisit this if the placeholder is ever removed.
- **`nexusagent-core`, `nexusagent-ai`** — equally valid, but `nexusagent-
  runtime` describes what the package actually is (an agent *runtime*) and
  was the first candidate that cleared verification.
- **Rename the import/package to something else entirely** — rejected: it
  would break the branding of the repository, the docs and the CLI for no
  functional gain.

## Consequences

- `pip install nexusagent-runtime`; `import nexusagent`. This asymmetry is
  intentional and documented in the README installation section.
- The PyPI/Python-versions README badges, `[project.urls]`, and the
  CHANGELOG all point at `nexusagent-runtime`.
- `tests/test_init.py` asserts `nexusagent.__version__` against
  `importlib.metadata.version("nexusagent-runtime")`, so a regression back to
  the old distribution name fails CI.
- If the `nexusagent` name ever becomes claimable (placeholder removed),
  migrating is a normal ADR-worthy decision — but this project will not
  squat or hoard names in the meantime.
