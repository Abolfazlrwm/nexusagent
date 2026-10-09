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
MAX_STEPS_LIMIT = 100


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
    system_prompt: str | None = None
    max_steps: int = 8

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from the current process environment."""
        return cls(
            env=os.getenv("NEXUS_ENV", "development"),
            log_level=os.getenv("NEXUS_LOG_LEVEL", "INFO"),
            model=os.getenv("NEXUS_MODEL"),
            api_key=os.getenv("NEXUS_API_KEY"),
            provider=os.getenv("NEXUS_PROVIDER", "fake"),
            endpoint=os.getenv("NEXUS_ENDPOINT"),
            timeout=float(os.getenv("NEXUS_TIMEOUT", "30.0")),
            system_prompt=os.getenv("NEXUS_SYSTEM_PROMPT"),
            max_steps=int(os.getenv("NEXUS_MAX_STEPS", "8")),
        )

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"Settings(env={self.env!r}, log_level={self.log_level!r}, "
            f"model={self.model!r}, api_key={api_key_display}, "
            f"provider={self.provider!r}, endpoint={self.endpoint!r}, "
            f"timeout={self.timeout!r}, "
            f"system_prompt={'set' if self.system_prompt else 'None'}, "
            f"max_steps={self.max_steps!r})"
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

        if self.system_prompt is not None and not self.system_prompt.strip():
            raise ValueError("System prompt must not be empty")

        if (
            isinstance(self.max_steps, bool)
            or not isinstance(self.max_steps, int)
            or not 1 <= self.max_steps <= MAX_STEPS_LIMIT
        ):
            raise ValueError(f"max_steps must be an integer between 1 and {MAX_STEPS_LIMIT}")

        if self.provider == "http" and not (self.endpoint and self.endpoint.strip()):
            raise ValueError("HTTP provider requires an endpoint")

        if self.provider in ("openai", "anthropic") and not (self.model and self.model.strip()):
            raise ValueError(f"{self.provider} provider requires a model")

        if self.provider == "anthropic" and not self.api_key:
            raise ValueError("anthropic provider requires an API key")

        # openai/anthropic fall back to their public endpoint when none is set.
        if self.provider == "http" or (self.provider in ("openai", "anthropic") and self.endpoint):
            scheme = urlparse(self.endpoint or "").scheme
            if scheme not in ("http", "https"):
                raise ValueError("Endpoint must use http or https")
