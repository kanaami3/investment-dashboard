"""Discord webhook notifier.

Setup:
1. Discord server → channel → ⚙ Integrations → Webhooks → New Webhook
2. Copy the webhook URL
3. Export as ``DISCORD_WEBHOOK_URL`` (or pass via constructor)

No bot token, no OAuth, no user ID needed — just the URL.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests

LOGGER = logging.getLogger(__name__)

_DISCORD_CONTENT_MAX = 2000


@dataclass
class DiscordConfig:
    webhook_url: str
    username: str = "stock-tools"
    timeout_sec: float = 10.0


class DiscordNotifier:
    def __init__(self, config: DiscordConfig):
        if not config.webhook_url or not config.webhook_url.startswith("https://discord.com/api/webhooks/"):
            raise ValueError("invalid discord webhook URL")
        self.config = config

    @classmethod
    def from_env(cls, env: str = "DISCORD_WEBHOOK_URL") -> "DiscordNotifier":
        url = os.environ.get(env)
        if not url:
            raise RuntimeError(f"env var {env} is not set")
        return cls(DiscordConfig(webhook_url=url))

    def send(self, content: str, embeds: list[dict] | None = None) -> None:
        """POST a message. Retries 429 / 5xx up to 3 times with backoff."""
        body: dict = {"username": self.config.username}
        if content:
            body["content"] = content[:_DISCORD_CONTENT_MAX]
        if embeds:
            body["embeds"] = embeds[:10]

        for attempt in range(3):
            try:
                resp = requests.post(
                    self.config.webhook_url,
                    json=body,
                    timeout=self.config.timeout_sec,
                )
            except requests.RequestException as e:
                LOGGER.warning("discord network error (attempt %d): %s", attempt + 1, e)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code in (200, 204):
                return
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                LOGGER.warning("discord 429, retry after %.1fs", retry_after)
                time.sleep(retry_after)
                continue
            if 500 <= resp.status_code < 600:
                LOGGER.warning("discord %d (attempt %d)", resp.status_code, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"discord webhook failed {resp.status_code}: {resp.text[:300]}")

        raise RuntimeError("discord webhook failed after 3 retries")


def format_signal_embed(
    symbol: str,
    name: str,
    decision: str,
    total: float,
    bull: float,
    bear: float,
    price: float,
    components: dict[str, float],
    extra_lines: list[str] | None = None,
) -> dict:
    color = {"LONG": 0x2ECC71, "SHORT": 0xE74C3C, "HOLD": 0x95A5A6}.get(decision, 0x95A5A6)
    desc_lines = [
        f"**Decision**: `{decision}`",
        f"**Score**: total={total:+.2f}  bull={bull:+.2f}  bear={bear:+.2f}",
        f"**Price**: {price:,.2f}",
    ]
    if extra_lines:
        desc_lines.extend(extra_lines)
    return {
        "title": f"{symbol} — {name}",
        "description": "\n".join(desc_lines),
        "color": color,
        "fields": [
            {"name": k, "value": f"{v:+.2f}", "inline": True}
            for k, v in components.items()
        ][:10],
    }
