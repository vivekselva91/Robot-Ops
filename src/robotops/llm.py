"""Thin wrapper around the Claude Messages API.

Two things matter here. First, every agent asks for JSON and gets a parsed dict
back, so downstream code never string-matches prose. Second, the wrapper runs
offline: with no API key it returns a deterministic stub, which keeps the demos
and the test suite usable without spending tokens.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .config import Config, load_config

JSON_RULE = (
    "Reply with a single JSON object and nothing else. No prose before or after, "
    "no markdown fences. If a field is unknown, use null rather than inventing a value."
)


class ClaudeClient:
    def __init__(self, config: Config | None = None, *, offline: bool = False) -> None:
        self.config = config or load_config()
        self.offline = offline or not self.config.live
        self._client = None
        if not self.offline:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on env
                raise RuntimeError(
                    "anthropic package missing. Install with: pip install -e '.[llm]'"
                ) from exc
            self._client = anthropic.Anthropic(api_key=self.config.api_key)

    def ask_json(
        self,
        system: str,
        user: str,
        *,
        fallback: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        """Send one prompt, return parsed JSON."""
        if self.offline:
            return {"offline": True, **(fallback or {})}

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=f"{system}\n\n{JSON_RULE}",
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                return _parse_json(text)
            except Exception as exc:  # noqa: BLE001 - surface any API/parse failure
                last_error = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Claude call failed after {retries + 1} attempts: {last_error}")


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model reply: {text[:200]}")
    return json.loads(text[start : end + 1])
