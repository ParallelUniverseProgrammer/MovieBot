from __future__ import annotations

import asyncio
import logging
import time
import contextlib
from typing import Any, Callable, Dict, List, Optional, Protocol


class ProgressSink(Protocol):
    async def emit(self, event_type: str, data: Any) -> None: ...

    async def typing_pulse(self) -> None: ...


class CallbackSink:
    """Adapter for legacy progress_callback(status: str, detail: str).

    Executes in a thread to avoid blocking the event loop.
    """

    def __init__(self, callback: Callable[[str, str], None]):
        self._callback = callback

    async def emit(self, event_type: str, data: Any) -> None:
        detail = data if isinstance(data, str) else (data.get("message") if isinstance(data, dict) and data.get("message") else str(data))
        try:
            await asyncio.to_thread(self._callback, event_type, detail)
        except Exception:
            # Never raise from UX updates
            pass

    async def typing_pulse(self) -> None:  # Legacy callback has no typing primitive
        return None


class AsyncProgressBroadcaster:
    """Throttled, multiplexed progress broadcaster for UI/Discord sinks.

    - Throttles high-frequency events (e.g., heartbeat)
    - Keeps lightweight background tasks for heartbeat and typing pulses
    - Never raises upstream; best-effort UX only
    """

    def __init__(
        self,
        *,
        throttle_interval_s: float = 0.9,
        heartbeat_interval_s: float = 1.2,
        typing_pulse_s: float = 7.5,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._sinks: List[ProgressSink] = []
        self._last_emit_per_type: Dict[str, float] = {}
        self._throttle_interval_s = float(throttle_interval_s)
        self._heartbeat_interval_s = float(heartbeat_interval_s)
        self._typing_pulse_s = float(typing_pulse_s)
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        self._log = logger or logging.getLogger("moviebot.progress")

    def add_sink(self, sink: ProgressSink) -> None:
        self._sinks.append(sink)

    async def emit(self, event_type: str, data: Any) -> None:
        # Unthrottled control events
        unthrottled = {"tool.start", "tool.finish", "tool.error", "llm.start", "llm.finish", "agent.start", "agent.finish"}
        now = time.monotonic()
        if event_type not in unthrottled:
            last = self._last_emit_per_type.get(event_type, 0.0)
            if (now - last) < self._throttle_interval_s:
                return
            self._last_emit_per_type[event_type] = now

        if not self._sinks:
            return
        # Build a single-sentence, humanized message
        payload = _humanize_event(event_type, data)

        async def _emit_one(sink: ProgressSink) -> None:
            try:
                await sink.emit(event_type, payload)
            except Exception:
                # Do not let UX failures bubble up
                pass

        await asyncio.gather(*[_emit_one(s) for s in self._sinks])

    def start_heartbeat(self, label: str = "agent") -> None:
        if label in self._heartbeat_tasks:
            return

        async def _hb() -> None:
            try:
                while True:
                    await self.emit("heartbeat", label)
                    await asyncio.sleep(self._heartbeat_interval_s)
            except asyncio.CancelledError:
                return

        self._heartbeat_tasks[label] = asyncio.create_task(_hb())

    def stop_heartbeat(self, label: str = "agent") -> None:
        task = self._heartbeat_tasks.pop(label, None)
        if task is not None:
            task.cancel()

    async def typing_start(self, scope: str = "llm") -> None:
        if scope in self._typing_tasks:
            return

        async def _pulse() -> None:
            try:
                while True:
                    await asyncio.gather(*[self._safe_typing(s) for s in self._sinks])
                    await asyncio.sleep(self._typing_pulse_s)
            except asyncio.CancelledError:
                return

        self._typing_tasks[scope] = asyncio.create_task(_pulse())

    async def typing_stop(self, scope: str = "llm") -> None:
        task = self._typing_tasks.pop(scope, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.sleep(0)  # let cancellation settle

    async def _safe_typing(self, sink: ProgressSink) -> None:
        try:
            await sink.typing_pulse()
        except Exception:
            pass

    async def aclose(self) -> None:
        for task in list(self._heartbeat_tasks.values()):
            task.cancel()
        for task in list(self._typing_tasks.values()):
            task.cancel()
        await asyncio.sleep(0)


def build_progress_broadcaster(project_root, legacy_callback: Optional[Callable[[str, str], None]] = None) -> AsyncProgressBroadcaster:
    """Factory that builds a broadcaster from runtime config, adding sinks.

    Adds:
    - Legacy callback sink if provided
    - Discord API sink if configured and aiohttp is available
    """
    # Local import to avoid import cycles at module import time
    from config.loader import load_runtime_config
    from integrations.discord_api import DiscordAPISink
    import contextlib

    rc = load_runtime_config(project_root)
    ux_cfg = rc.get("ux", {}) or {}
    discord_cfg = rc.get("discord", {}) or {}

    throttle_interval_s = float(ux_cfg.get("progressUpdateIntervalMs", 900)) / 1000.0
    heartbeat_interval_s = float(ux_cfg.get("heartbeatIntervalMs", 1200)) / 1000.0
    typing_pulse_s = float(ux_cfg.get("typingPulseMs", 7500)) / 1000.0

    broadcaster = AsyncProgressBroadcaster(
        throttle_interval_s=throttle_interval_s,
        heartbeat_interval_s=heartbeat_interval_s,
        typing_pulse_s=typing_pulse_s,
    )

    if legacy_callback is not None:
        broadcaster.add_sink(CallbackSink(legacy_callback))

    # Optional Discord sink
    enabled = bool(discord_cfg.get("enabled", False))
    if enabled:
        token = discord_cfg.get("botToken") or ""
        channel_id = discord_cfg.get("channelId") or ""
        webhook_url = discord_cfg.get("webhookUrl") or None
        if token and channel_id:
            try:
                broadcaster.add_sink(DiscordAPISink(token=token, channel_id=str(channel_id), webhook_url=webhook_url))
            except Exception:
                # If Discord fails to init, continue without it
                pass

    return broadcaster


def _humanize_event(event_type: str, data: Any) -> Dict[str, Any]:
    """Return a payload with a single-sentence, descriptive 'message'."""
    try:
        base: Dict[str, Any] = {"event": event_type, "data": data}
        name = None
        if isinstance(data, dict):
            name = data.get("name") or data.get("tool")
        # Event-specific messages
        if event_type == "agent.start":
            par = _safe_get(data, "parallelism")
            iters = _safe_get(data, "iters")
            base["message"] = f"Kicking off a plan and launching up to {par} tasks in parallel for {iters} steps."
        elif event_type == "thinking":
            it = _safe_get(data, "iteration")
            base["message"] = f"Thinking through options (iteration {it}) with a bias for decisive parallel moves."
        elif event_type == "llm.start":
            model = _safe_get(data, "model")
            base["message"] = f"Consulting {model} to sketch the best next set of actions."
        elif event_type == "llm.finish":
            base["message"] = "LLM plan refined; executing the most promising actions now."
        elif event_type == "tool.start":
            pretty = _pretty_tool_name(name or "tool")
            base["message"] = f"Starting {pretty} to advance the goal."
        elif event_type == "tool.finish":
            pretty = _pretty_tool_name(name or "tool")
            dur = _safe_get(data, "duration_ms")
            base["message"] = f"Finished {pretty} in {dur} ms; folding results into the plan."
        elif event_type == "tool.error":
            pretty = _pretty_tool_name(name or "tool")
            base["message"] = f"{pretty} hit a snag; recovering with retries or alternatives."
        elif event_type == "heartbeat":
            base["message"] = "Still working—keeping things moving in the background."
        elif event_type == "agent.finish":
            reason = _safe_get(data, "reason")
            if reason == "final_answer":
                base["message"] = "Wrapping up—returning the final picks now."
            else:
                base["message"] = "Reached the iteration limit—delivering the best available result."
        else:
            base["message"] = f"{event_type.replace('.', ' ').title()} in progress."
        return base
    except Exception:
        return {"event": event_type, "data": data, "message": "Working on it."}


def _safe_get(data: Any, key: str) -> str:
    try:
        if isinstance(data, dict):
            val = data.get(key)
            if val is None:
                return "unknown"
            return str(val)
        return str(data)
    except Exception:
        return "unknown"


def _pretty_tool_name(raw: str) -> str:
    r = str(raw)
    if r.startswith("tmdb_"):
        if "search" in r:
            return "TMDb search"
        if "discover" in r:
            return "TMDb discovery"
        if "details" in r or "get_" in r:
            return "TMDb details fetch"
        return "TMDb call"
    if r.startswith("plex_") or r.startswith("get_plex"):
        return "Plex library scan"
    if r.startswith("radarr_"):
        return "Radarr add"
    if r.startswith("sonarr_"):
        return "Sonarr add"
    return r.replace('_', ' ')


