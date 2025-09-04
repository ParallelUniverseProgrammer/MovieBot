from __future__ import annotations

import logging
from typing import Any, Optional


class DiscordAPISink:
    """Minimal async Discord sink using aiohttp if available.

    Capabilities:
    - Send lightweight progress messages
    - Emit typing indicators via REST (bots only)
    - Connection pooling for efficiency

    Falls back to no-op if aiohttp is not installed.
    """

    def __init__(self, *, token: str, channel_id: str, webhook_url: Optional[str] = None) -> None:
        self._token = token
        self._channel_id = channel_id
        self._webhook_url = webhook_url
        self._log = logging.getLogger("moviebot.discord")
        self._session: Optional[Any] = None
        try:
            import aiohttp  # noqa: F401
            self._aiohttp_available = True
        except Exception:
            self._aiohttp_available = False
            self._log.warning("aiohttp not installed; Discord sink disabled")

    async def _get_session(self) -> Any:
        """Get or create aiohttp session with connection pooling."""
        if not self._aiohttp_available:
            return None
        if self._session is None or self._session.closed:
            import aiohttp
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._session

    async def aclose(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

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
        session = await self._get_session()
        if not session:
            return
        try:
            if self._webhook_url:
                await session.post(self._webhook_url, json={"content": content})
            else:
                # Bot token + channel message
                url = f"https://discord.com/api/v10/channels/{self._channel_id}/messages"
                headers = {"Authorization": f"Bot {self._token}"}
                await session.post(url, headers=headers, json={"content": content})
        except Exception:
            # Silent failure for UX updates
            pass

    async def _typing_once(self) -> None:
        if not self._aiohttp_available:
            return
        session = await self._get_session()
        if not session:
            return
        try:
            url = f"https://discord.com/api/v10/channels/{self._channel_id}/typing"
            headers = {"Authorization": f"Bot {self._token}"}
            await session.post(url, headers=headers)
        except Exception:
            # Silent failure for UX updates
            pass


