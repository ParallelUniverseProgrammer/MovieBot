from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
import asyncio
import logging

from llm.clients import LLMClient
from .agent_prompt import AGENT_SYSTEM_PROMPT
from .tools.registry import build_openai_tools_and_registry
from .tools.tool_impl import build_preferences_context  # reuse the same formatter


class Agent:
    def __init__(self, *, api_key: str, project_root: Path):
        self.llm = LLMClient(api_key)
        self.openai_tools, self.tool_registry = build_openai_tools_and_registry(project_root, self.llm)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.agent")

    def _chat_once(self, messages: List[Dict[str, Any]], model: str) -> Any:
        self.log.debug("LLM.chat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            tool_choice="auto",
            temperature=1,  # per current API constraints
        )
        try:
            content_preview = (resp.choices[0].message.content or "")[:120]  # type: ignore[attr-defined]
        except Exception:
            content_preview = "<no content>"
        self.log.debug("LLM.chat done", extra={
            "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),  # type: ignore[attr-defined]
            "content_preview": content_preview,
        })
        return resp

    def _run_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, max_iters: int = 4) -> Any:
        # System message + optional dynamic household preferences context (for recommendations)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        if model == "gpt-5":
            try:
                prefs_path = self.project_root / "data" / "household_preferences.json"
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
                compact = build_preferences_context(prefs)
                if compact.strip():
                    messages.append({
                        "role": "system",
                        "content": "Household preferences (compact):\n" + compact
                    })
            except Exception:
                # Non-fatal if prefs missing or unparsable
                pass
        messages += base_messages
        last_response: Any = None
        for iter_idx in range(max_iters):
            self.log.info(f"agent iteration {iter_idx+1}/{max_iters}")
            last_response = self._chat_once(messages, model)
            choice = last_response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                self.log.info("no tool calls; returning final answer")
                return last_response
            # Append assistant message that contains tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            # Execute each tool sequentially
            for tc in tool_calls:
                name = tc.function.name
                args_json = tc.function.arguments or "{}"
                self.log.info(f"tool call requested: {name}")
                self.log.debug("tool args", extra={"name": name, "args": args_json})
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError:
                    args = {}
                impl = self.tool_registry.get(name)
                # Run async tool in its own loop (safe in this thread)
                try:
                    result = asyncio.run(impl(args))
                    self.log.info(f"tool result: {name} ok")
                    self.log.debug("tool result payload", extra={"name": name, "result": result})
                except Exception as e:  # noqa: BLE001
                    self.log.exception(f"tool execution failed: {name}: {e}")
                    result = {"ok": False, "error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result),
                })
        return last_response

    def converse(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return self._run_tools_loop(messages, model="gpt-5-mini")

    def recommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return self._run_tools_loop(messages, model="gpt-5")


