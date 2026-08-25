from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class ProviderConfig:
    model: str | None = None
    api_key: str | None = None
    endpoint: str | None = None
    timeout: float = 30.0

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return (
            f"ProviderConfig(model={self.model!r}, api_key={api_key_display}, "
            f"endpoint={self.endpoint!r}, timeout={self.timeout!r})"
        )


class Provider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...


class ProviderError(Exception):
    """Base exception for provider-related failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider configuration is invalid for a provider."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request fails."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response is invalid."""
