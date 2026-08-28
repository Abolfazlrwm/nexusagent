from __future__ import annotations

from nexusagent.tool import Tool


class EchoTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="echo", description="Returns its input unchanged.")

    def execute(self, input_data: str) -> str:
        return input_data
