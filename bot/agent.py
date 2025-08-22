from __future__ import annotations

from typing import Any, Dict, List, Callable, Optional
from pathlib import Path
import json
import asyncio
import logging

from llm.clients import LLMClient
from .agent_prompt import AGENT_SYSTEM_PROMPT
from .tools.registry import build_openai_tools_and_registry
from .tools.tool_impl import build_preferences_context  # reuse the same formatter
from config.loader import load_runtime_config
from config.loader import load_runtime_config


class Agent:
    def __init__(self, *, api_key: str, project_root: Path, provider: str = "openai", progress_callback: Optional[Callable[[str, str], None]] = None):
        self.llm = LLMClient(api_key, provider=provider)
        self.openai_tools, self.tool_registry = build_openai_tools_and_registry(project_root, self.llm)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.agent")
        self.progress_callback = progress_callback

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
            temperature=1,  # gpt-5 family requires 1
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

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        self.log.debug("LLM.achat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        resp = await self.llm.achat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            tool_choice="auto",
            temperature=1,  # gpt-5 family requires 1
        )

        try:
            content_preview = (resp.choices[0].message.content or "")[:120]  # type: ignore[attr-defined]
        except Exception:
            content_preview = "<no content>"
        self.log.debug("LLM.achat done", extra={
            "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),  # type: ignore[attr-defined]
            "content_preview": content_preview,
        })
        return resp

    def _run_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, max_iters: int | None = None) -> Any:
        # Load runtime config for loop controls
        rc = load_runtime_config(self.project_root)
        cfg_max_iters = int(rc.get("llm", {}).get("maxIters", 8))
        iters = max_iters or cfg_max_iters
        # System message + optional dynamic household preferences context (for recommendations)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        
        # Check if we should add household preferences context
        # For OpenAI GPT-5 models or OpenRouter models that support reasoning
        should_add_prefs = (
            model == "gpt-5" or 
            (hasattr(self.llm, 'provider') and self.llm.provider == "openrouter" and "glm-4.5" in model)
        )
        
        if should_add_prefs:
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
        for iter_idx in range(iters):
            self.log.info(f"agent iteration {iter_idx+1}/{iters}")
            
            # Notify progress callback about LLM thinking
            if self.progress_callback:
                try:
                    self.progress_callback("thinking", f"iteration {iter_idx+1}/{iters}")
                except Exception:
                    pass  # Don't let progress updates break the main flow
            
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
            # Execute tool calls concurrently with bounded parallelism
            rc = load_runtime_config(self.project_root)
            timeout_ms = int(rc.get("tools", {}).get("timeoutMs", 8000))
            parallelism = int(rc.get("tools", {}).get("parallelism", 4))
            retry_max = int(rc.get("tools", {}).get("retryMax", 2))
            backoff_base_ms = int(rc.get("tools", {}).get("backoffBaseMs", 200))

            async def run_one(tc):
                name = tc.function.name
                args_json = tc.function.arguments or "{}"
                self.log.info(f"tool call requested: {name}")
                self.log.debug("tool args", extra={"name": name, "args": args_json})
                
                # Notify progress callback about tool execution
                if self.progress_callback:
                    try:
                        self.progress_callback("tool", name)
                    except Exception:
                        pass
                
                # Parse args
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    payload = {"ok": False, "error": "invalid_json", "details": str(e)}
                    return tc.id, name, payload, 0, False

                # Execute with retries/backoff, timeout, and timing
                attempt = 0
                import time
                start = time.monotonic()
                cache_hit = False
                last_err = None

                async def attempt_once():
                    try:
                        return await asyncio.wait_for(self.tool_registry.get(name)(args), timeout=timeout_ms / 1000)
                    except asyncio.TimeoutError as e:
                        raise e

                while True:
                    try:
                        result = await attempt_once()
                        status = "ok"
                        break
                    except asyncio.TimeoutError as e:
                        last_err = {"ok": False, "error": "timeout", "timeout_ms": timeout_ms, "name": name}
                    except Exception as e:
                        last_err = {"ok": False, "error": str(e)}
                    if attempt >= retry_max:
                        result = last_err
                        status = "error"
                        break
                    # backoff with jitter
                    jitter = (attempt + 1) * 0.1
                    await asyncio.sleep((backoff_base_ms / 1000) * (2 ** attempt) + jitter)
                    attempt += 1
                duration_ms = int((time.monotonic() - start) * 1000)
                self.log.info("tool done", extra={"name": name, "status": status, "duration_ms": duration_ms, "attempts": attempt + 1, "cache_hit": cache_hit})
                return tc.id, name, result, attempt + 1, cache_hit

            # Run with bounded concurrency
            sem = asyncio.Semaphore(parallelism)

            async def sem_wrapped(tc):
                async with sem:
                    return await run_one(tc)

            async def run_all():
                return await asyncio.gather(*[sem_wrapped(tc) for tc in tool_calls])

            # Always spin a private loop in a new thread to avoid nested-loop issues
            import threading

            results_container = {}
            def runner():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results_container['results'] = loop.run_until_complete(run_all())
                finally:
                    loop.close()

            t = threading.Thread(target=runner)
            t.start()
            t.join()
            results = results_container.get('results', [])
            for tool_call_id, name, result, attempts, cache_hit in results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(result),
                })
            # Finalization turn after tools: ask model to produce a user-facing reply
            final_resp = self._chat_once(messages, model)
            try:
                final_tc = getattr(final_resp.choices[0].message, "tool_calls", None)
            except Exception:
                final_tc = None
            if not final_tc:
                return final_resp
        # If we exhausted iterations and still have tool calls requested, synthesize a graceful reply
        synthesized = {
            "choices": [
                {
                    "message": {
                        "content": "This needs a few more steps. Want me to continue?"
                    }
                }
            ]
        }
        return synthesized  # type: ignore[return-value]

    async def _arun_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, max_iters: int | None = None) -> Any:
        """Async version of _run_tools_loop for non-blocking operations."""
        # Load runtime config for loop controls
        rc = load_runtime_config(self.project_root)
        cfg_max_iters = int(rc.get("llm", {}).get("maxIters", 8))
        iters = max_iters or cfg_max_iters
        # System message + optional dynamic household preferences context (for recommendations)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        
        # Check if we should add household preferences context
        # For OpenAI GPT-5 models or OpenRouter models that support reasoning
        should_add_prefs = (
            model == "gpt-5" or 
            (hasattr(self.llm, 'provider') and self.llm.provider == "openrouter" and "glm-4.5" in model)
        )
        
        if should_add_prefs:
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
        for iter_idx in range(iters):
            self.log.info(f"agent iteration {iter_idx+1}/{iters}")
            
            # Notify progress callback about LLM thinking
            if self.progress_callback:
                try:
                    self.progress_callback("thinking", f"iteration {iter_idx+1}/{iters}")
                except Exception:
                    pass  # Don't let progress updates break the main flow
            
            last_response = await self._achat_once(messages, model)
            choice = last_response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, 'tool_calls', None)
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
            # Execute tool calls concurrently with bounded parallelism
            rc = load_runtime_config(self.project_root)
            timeout_ms = int(rc.get("tools", {}).get("timeoutMs", 8000))
            parallelism = int(rc.get("tools", {}).get("parallelism", 4))
            retry_max = int(rc.get("tools", {}).get("retryMax", 2))
            backoff_base_ms = int(rc.get("tools", {}).get("backoffBaseMs", 200))

            async def run_one(tc):
                name = tc.function.name
                args_json = tc.function.arguments or "{}"
                self.log.info(f"tool call requested: {name}")
                self.log.debug("tool args", extra={"name": name, "args": args_json})
                
                # Notify progress callback about tool execution
                if self.progress_callback:
                    try:
                        self.progress_callback("tool", name)
                    except Exception:
                        pass
                
                # Parse args
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    payload = {"ok": False, "error": "invalid_json", "details": str(e)}
                    return tc.id, name, payload, 0, False

                # Execute with retries/backoff, timeout, and timing
                attempt = 0
                import time
                start = time.monotonic()
                cache_hit = False
                last_err = None

                async def attempt_once():
                    try:
                        return await asyncio.wait_for(self.tool_registry.get(name)(args), timeout=timeout_ms / 1000)
                    except asyncio.TimeoutError as e:
                        raise e

                while True:
                    try:
                        result = await attempt_once()
                        status = "ok"
                        break
                    except asyncio.TimeoutError as e:
                        last_err = {"ok": False, "error": "timeout", "timeout_ms": timeout_ms, "name": name}
                    except Exception as e:
                        last_err = {"ok": False, "error": str(e)}
                    if attempt >= retry_max:
                        result = last_err
                        status = "error"
                        break
                    # backoff with jitter
                    jitter = (attempt + 1) * 0.1
                    await asyncio.sleep((backoff_base_ms / 1000) * (2 ** attempt) + jitter)
                    attempt += 1
                duration_ms = int((time.monotonic() - start) * 1000)
                self.log.info("tool done", extra={"name": name, "status": status, "duration_ms": duration_ms, "attempts": attempt + 1, "cache_hit": cache_hit})
                return tc.id, name, result, attempt + 1, cache_hit

            # Run with bounded concurrency
            sem = asyncio.Semaphore(parallelism)

            async def sem_wrapped(tc):
                async with sem:
                    return await run_one(tc)

            # Execute all tool calls concurrently
            results = await asyncio.gather(*[sem_wrapped(tc) for tc in tool_calls])
            
            for tool_call_id, name, result, attempts, cache_hit in results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(result),
                })
            # Finalization turn after tools: ask model to produce a user-facing reply
            final_resp = await self._achat_once(messages, model)
            try:
                final_tc = getattr(final_resp.choices[0].message, "tool_calls", None)
            except Exception:
                final_tc = None
            if not final_tc:
                return final_resp
        # If we exhausted iterations and still have tool calls requested, synthesize a graceful reply
        synthesized = {
            "choices": [
                {
                    "message": {
                        "content": "This needs a few more steps. Want me to continue?"
                    }
                }
            ]
        }
        return synthesized  # type: ignore[return-value]

    def converse(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # Choose appropriate model based on provider
        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"  # Use the free GLM 4.5 Air model for conversations
        else:
            model = "gpt-5-mini"  # Fallback to OpenAI model
        return self._run_tools_loop(messages, model=model)

    async def aconverse(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Async version of converse for non-blocking operations."""
        # Choose appropriate model based on provider
        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"  # Use the free GLM 4.5 Air model for conversations
        else:
            model = "gpt-5-mini"  # Fallback to OpenAI model
        return await self._arun_tools_loop(messages, model=model)

    def recommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # Choose appropriate model based on provider
        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"  # Use the free GLM 4.5 Air model for recommendations
        else:
            model = "gpt-5"  # Fallback to OpenAI model
        return self._run_tools_loop(messages, model=model)

    async def arecommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Async version of recommend for non-blocking operations."""
        # Choose appropriate model based on provider
        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"  # Use the free GLM 4.5 Air model for recommendations
        else:
            model = "gpt-5"  # Fallback to OpenAI model
        return await self._arun_tools_loop(messages, model=model)


