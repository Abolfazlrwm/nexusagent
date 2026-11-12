"""Application configuration for NexusAgent.

Settings are read from environment variables. No .env loading and no
external configuration frameworks are used at this stage.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from urllib.parse import urlparse

SUPPORTED_PROVIDERS = {"fake", "http", "openai", "anthropic"}


@dataclass(frozen=True, repr=False)
class Settings:
    """Basic application settings, loaded from environment variables."""

    env: str = "development"
    log_level: str = "INFO"
    model: str | None = None
    api_key: str | None = None
    provider: str = "fake"
    endpoint: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from the current process environment."""
        raw_timeout = os.getenv("NEXUS_TIMEOUT", "30.0")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            raise ValueError(
                f"Invalid NEXUS_TIMEOUT: {raw_timeout!r} — "
                "must be a number of seconds (e.g. 30 or 4.5)"
            ) from None

        return cls(
            env=os.getenv("NEXUS_ENV", "development"),
            log_level=os.getenv("NEXUS_LOG_LEVEL", "INFO"),
            model=os.getenv("NEXUS_MODEL"),
            api_key=os.getenv("NEXUS_API_KEY"),
            provider=os.getenv("NEXUS_PROVIDER", "fake"),
            endpoint=os.getenv("NEXUS_ENDPOINT"),
            timeout=timeout,
        )

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"Settings(env={self.env!r}, log_level={self.log_level!r}, "
            f"model={self.model!r}, api_key={api_key_display}, "
            f"provider={self.provider!r}, endpoint={self.endpoint!r}, "
            f"timeout={self.timeout!r})"
        )

    def validate(self) -> None:
        """Validate the configuration locally, without any network access.

        Raises ValueError with a clear, safe message on the first
        problem found. Never includes the API key.
        """
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {self.provider!r}")

        if self.model is not None and not self.model.strip():
            raise ValueError("Model must not be empty")

        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Timeout must be a positive finite number")

        if self.provider == "http" and (not self.endpoint or not self.endpoint.strip()):
            raise ValueError("HTTP provider requires an endpoint")

        if self.provider == "openai" and self.model is None:
            raise ValueError("OpenAI provider requires a model")

        if self.provider == "anthropic" and self.model is None:
            raise ValueError("Anthropic provider requires a model")

        if self.endpoint is not None:
            scheme = urlparse(self.endpoint).scheme
            if scheme not in ("http", "https"):
                raise ValueError("Endpoint must use http or https")
