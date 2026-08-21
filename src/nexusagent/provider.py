from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class ProviderConfig:
    model: str | None = None
    api_key: str | None = None

    def __repr__(self) -> str:
        api_key_display = "set" if self.api_key else "None"
        return f"ProviderConfig(model={self.model!r}, api_key={api_key_display})"


class Provider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...
