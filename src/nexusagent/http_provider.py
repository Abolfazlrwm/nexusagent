from __future__ import annotations

import json
import urllib.error
import urllib.request

from nexusagent.provider import Provider, ProviderConfig


class HttpProvider(Provider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        self.config = config or ProviderConfig()

    def generate(self, prompt: str) -> str:
        if not self.config.endpoint:
            raise ValueError("HttpProvider requires a configured endpoint")

        if self.config.timeout <= 0:
            raise ValueError("HttpProvider requires a positive timeout")

        body = json.dumps({"model": self.config.model, "input": prompt}).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        request = urllib.request.Request(
            self.config.endpoint, data=body, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP request failed with status {exc.code}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"HTTP request failed: {exc.reason}") from None
        except TimeoutError:
            raise RuntimeError("HTTP request timed out") from None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("HTTP response was not valid JSON") from None

        if not isinstance(payload, dict):
            raise RuntimeError("HTTP response must be a JSON object")  # noqa: TRY004

        if "output" not in payload:
            raise RuntimeError("HTTP response is missing the 'output' field")

        output = payload["output"]
        if not isinstance(output, str):
            raise RuntimeError("HTTP response 'output' field must be a string")  # noqa: TRY004

        if not output.strip():
            raise RuntimeError("HTTP response 'output' field must not be empty")

        return output
