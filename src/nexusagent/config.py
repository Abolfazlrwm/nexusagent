"""Application configuration for NexusAgent.

Settings are read from environment variables. No .env loading and no
external configuration frameworks are used at this stage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class Settings:
    """Basic application settings, loaded from environment variables."""

    env: str = "development"
    log_level: str = "INFO"
    model: str | None = None
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        """Build Settings from the current process environment."""
        return cls(
            env=os.getenv("NEXUS_ENV", "development"),
            log_level=os.getenv("NEXUS_LOG_LEVEL", "INFO"),
            model=os.getenv("NEXUS_MODEL"),
            api_key=os.getenv("NEXUS_API_KEY"),
        )

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"Settings(env={self.env!r}, log_level={self.log_level!r}, "
            f"model={self.model!r}, api_key={api_key_display})"
        )
