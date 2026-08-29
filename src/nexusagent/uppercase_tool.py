from __future__ import annotations

from nexusagent.tool import Tool


class UppercaseTool(Tool):
    def __init__(self) -> None:
        super().__init__(name="uppercase", description="Converts input to uppercase.")

    def execute(self, input_data: str) -> str:
        return input_data.upper()
