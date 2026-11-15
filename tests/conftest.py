"""Shared fixtures for the test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_retry_backoff(monkeypatch):
    """Make the transport retry backoff instant.

    Retry delays (ADR 0011) are wall-clock sleeps in the shared transport;
    unit tests assert the delays via an explicit patched ``time.sleep``
    where it matters. This fixture makes every other test that exercises
    error paths run instantly instead of actually sleeping through
    backoff windows.
    """
    monkeypatch.setattr("nexusagent.http_provider.time.sleep", lambda _seconds: None)
