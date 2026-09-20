"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-sonnet-5"


@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str
    max_tokens: int
    slack_webhook: str | None
    discord_webhook: str | None

    @property
    def live(self) -> bool:
        """True when a real Claude call is possible."""
        return bool(self.api_key)


def load_config() -> Config:
    _load_dotenv()
    return Config(
        api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        model=os.getenv("ROBOTOPS_MODEL", DEFAULT_MODEL),
        max_tokens=int(os.getenv("ROBOTOPS_MAX_TOKENS", "2000")),
        slack_webhook=os.getenv("ROBOTOPS_SLACK_WEBHOOK") or None,
        discord_webhook=os.getenv("ROBOTOPS_DISCORD_WEBHOOK") or None,
    )


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env reader so the package stays dependency-free."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
