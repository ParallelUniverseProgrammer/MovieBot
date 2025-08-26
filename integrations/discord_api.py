from __future__ import annotations

import logging
from typing import Any, Optional


class DiscordAPISink:
    """Minimal async Discord sink using aiohttp if available.

    Capabilities:
    - Send lightweight progress messages
    - Emit typing indicators via REST (bots only)

    Falls back to no-op if aiohttp is not installed.
    """

    def __init__(self, *, token: str, channel_id: str, webhook_url: Optional[str] = None) -> None:
        self._token = token
        self._channel_id = channel_id
        self._webhook_url = webhook_url
        self._log = logging.getLogger("moviebot.discord")
        try:
            import aiohttp  # noqa: F401
            self._aiohttp_available = True
        except Exception:
            self._aiohttp_available = False
            self._log.warning("aiohttp not installed; Discord sink disabled")

    async def emit(self, event_type: str, data: Any) -> None:
        if not self._aiohttp_available:
            return
        try:
            if event_type == "heartbeat":
                return
            message = None
            if isinstance(data, dict):
                message = data.get("message")
            if not message:
                message = f"{event_type.replace('.', ' ').title()} in progress."
            if event_type == "llm.start":
                await self._typing_once()
            await self._send_message(message)
        except Exception:
            # Silent failure; UX only
            pass

    async def typing_pulse(self) -> None:
        if not self._aiohttp_available:
            return
        try:
            await self._typing_once()
        except Exception:
            pass

    async def _send_message(self, content: str) -> None:
        if not self._aiohttp_available:
            return
        import aiohttp
        if self._webhook_url:
            async with aiohttp.ClientSession() as session:
                await session.post(self._webhook_url, json={"content": content})
            return
        # Bot token + channel message
        url = f"https://discord.com/api/v10/channels/{self._channel_id}/messages"
        headers = {"Authorization": f"Bot {self._token}"}
        async with aiohttp.ClientSession() as session:
            await session.post(url, headers=headers, json={"content": content})

    async def _typing_once(self) -> None:
        if not self._aiohttp_available:
            return
        import aiohttp
        url = f"https://discord.com/api/v10/channels/{self._channel_id}/typing"
        headers = {"Authorization": f"Bot {self._token}"}
        async with aiohttp.ClientSession() as session:
            await session.post(url, headers=headers)


