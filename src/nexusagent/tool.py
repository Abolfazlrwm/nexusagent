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


class AsyncTool(Tool):
    """A tool whose body is awaited, for the async execution layer.

    ``AsyncTool`` extends the sync ``Tool`` ABC: ``name`` and ``description``
    work everywhere, but the implementation lives in ``aexecute()``. The sync
    ``ToolExecutor`` and the sync ``Agent`` cannot await it, so ``execute()``
    fails fast with a clear ``NotImplementedError`` instead of silently
    producing an un-awaited coroutine object. Run async tools through
    ``AsyncToolExecutor`` (``AsyncAgent`` / ``create_async_runtime``).
    """

    @abstractmethod
    async def aexecute(self, input_data: str) -> str: ...

    def execute(self, input_data: str) -> str:
        raise NotImplementedError(
            f"AsyncTool {self.name!r} cannot run on the sync path; "
            "use AsyncToolExecutor (AsyncAgent / create_async_runtime)"
        )
