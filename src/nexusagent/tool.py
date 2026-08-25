from __future__ import annotations

from abc import ABC, abstractmethod


class Tool(ABC):
    def __init__(self, name: str, description: str) -> None:
        if not isinstance(name, str):
            raise TypeError("Tool name must be a string")

        if not name.strip():
            raise ValueError("Tool name must not be empty or whitespace-only")

        if not isinstance(description, str):
            raise TypeError("Tool description must be a string")

        if not description.strip():
            raise ValueError("Tool description must not be empty or whitespace-only")

        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, input_data: str) -> str: ...
