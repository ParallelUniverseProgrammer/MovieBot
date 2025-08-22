from __future__ import annotations

from typing import Any, Dict, List, Callable, Optional
from pathlib import Path
import json
import asyncio
import logging
import threading

from llm.clients import LLMClient
from .agent_prompt import AGENT_SYSTEM_PROMPT
from .tools.registry import build_openai_tools_and_registry
from .tools.tool_impl import build_preferences_context  # reuse the same formatter
from config.loader import load_runtime_config
from config.loader import resolve_llm_provider_and_model


class Agent:
    def __init__(self, *, api_key: str, project_root: Path, provider: str = "openai", progress_callback: Optional[Callable[[str, str], None]] = None):
        # Override provider by config priority if available
        from config.loader import resolve_llm_selection, load_settings
        prov, _sel = resolve_llm_selection(project_root, "chat", load_settings(project_root))
        self.llm = LLMClient(api_key, provider=prov)
        self.openai_tools, self.tool_registry = build_openai_tools_and_registry(project_root, self.llm)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.agent")
        self.progress_callback = progress_callback

    def _chat_once(self, messages: List[Dict[str, Any]], model: str, role: str) -> Any:
        self.log.debug("LLM.chat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        # Pull optional reasoningEffort/params for role from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, role)
        params = dict(sel.get("params", {}))
        params.setdefault("temperature", 1)
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            reasoning=sel.get("reasoningEffort"),
            tool_choice=params.pop("tool_choice", "auto"),
            **params,
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

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str, role: str) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        self.log.debug("LLM.achat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        if hasattr(self.llm, "achat"):
            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, role)
            params = dict(sel.get("params", {}))
            params.setdefault("temperature", 1)
            resp = await self.llm.achat(
                model=model,
                messages=messages,
                tools=self.openai_tools,
                reasoning=sel.get("reasoningEffort"),
                tool_choice=params.pop("tool_choice", "auto"),
                **params,
            )
        else:
            # Fallback: run sync client.chat in a thread to avoid blocking the event loop
            import functools
            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, role)
            params = dict(sel.get("params", {}))
            params.setdefault("temperature", 1)
            fn = functools.partial(
                self.llm.chat,
                model=model,
                messages=messages,
                tools=self.openai_tools,
                reasoning=sel.get("reasoningEffort"),
                tool_choice=params.pop("tool_choice", "auto"),
                **params,
            )
            resp = await asyncio.to_thread(fn)

        try:
            content_preview = (resp.choices[0].message.content or "")[:120]  # type: ignore[attr-defined]
        except Exception:
            content_preview = "<no content>"
        self.log.debug("LLM.achat done", extra={
            "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),  # type: ignore[attr-defined]
            "content_preview": content_preview,
        })
        return resp

    async def _run_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, role: str, max_iters: int | None = None) -> Any:
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
            
            last_response = await self._achat_once(messages, model, role)
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
            # Execute tool calls concurrently with bounded parallelism and batching
            rc = load_runtime_config(self.project_root)
            timeout_ms = int(rc.get("tools", {}).get("timeoutMs", 8000))
            parallelism = int(rc.get("tools", {}).get("parallelism", 4))
            retry_max = int(rc.get("tools", {}).get("retryMax", 2))
            backoff_base_ms = int(rc.get("tools", {}).get("backoffBaseMs", 200))

            # Group tool calls by type for potential batching
            tool_groups = self._group_tool_calls_for_batching(tool_calls)
            
            async def run_one_or_batch(tc_or_group):
                if isinstance(tc_or_group, list):
                    # Batch execution
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms)
                else:
                    # Single tool execution
                    return await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms)

            # Run with bounded concurrency
            sem = asyncio.Semaphore(parallelism)

            async def sem_wrapped(tc_or_group):
                async with sem:
                    return await run_one_or_batch(tc_or_group)

            # Execute all tools (single or batched) concurrently
            results = await asyncio.gather(*[sem_wrapped(tc_or_group) for tc_or_group in tool_groups])
            
            # Flatten results from batched executions
            flattened_results = []
            for result in results:
                if isinstance(result, list):
                    flattened_results.extend(result)
                else:
                    flattened_results.append(result)
            for tool_call_id, name, result, attempts, cache_hit in flattened_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(result),
                })
            # Finalization turn after tools: ask model to produce a user-facing reply
            final_resp = await self._achat_once(messages, model, role)
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

    def _group_tool_calls_for_batching(self, tool_calls: List[Any]) -> List[Any]:
        """Group tool calls by type for potential batching.
        
        Returns a list where each element is either a single tool call or a list of tool calls
        that can be executed as a batch.
        """
        # Group by tool name and similar parameters for potential batching
        tool_groups = {}
        
        for tc in tool_calls:
            name = tc.function.name
            args = tc.function.arguments or "{}"
            
            # Create a key for grouping based on tool name and similar parameters
            if name.startswith("tmdb_"):
                # Group TMDB calls by type (search, details, etc.)
                group_key = f"tmdb_{name.split('_', 1)[1]}"
            elif name.startswith("plex_"):
                # Group Plex calls by type
                group_key = f"plex_{name.split('_', 1)[1]}"
            elif name.startswith("radarr_") or name.startswith("sonarr_"):
                # Group Radarr/Sonarr calls by type
                group_key = f"{name.split('_', 1)[0]}_{name.split('_', 1)[1]}"
            else:
                # Keep other tools as single executions
                group_key = name
            
            if group_key not in tool_groups:
                tool_groups[group_key] = []
            tool_groups[group_key].append(tc)
        
        # Convert to list format, keeping single tools as-is and grouping similar ones
        result = []
        for group_key, tools in tool_groups.items():
            if len(tools) == 1:
                result.append(tools[0])  # Single tool
            elif len(tools) > 1 and self._can_batch_tools(tools):
                result.append(tools)  # Batchable group
            else:
                # Can't batch, add individually
                result.extend(tools)
        
        return result

    def _can_batch_tools(self, tools: List[Any]) -> bool:
        """Check if a group of tools can be executed as a batch."""
        if len(tools) < 2:
            return False
        
        # Check if all tools have the same name and similar structure
        first_tool = tools[0]
        first_name = first_tool.function.name
        
        for tool in tools[1:]:
            if tool.function.name != first_name:
                return False
        
        # Only batch certain tool types that support it
        batchable_tools = {
            "tmdb_search", "tmdb_discover_movies", "tmdb_discover_tv",
            "plex_search", "get_plex_library_sections"
        }
        
        return first_name in batchable_tools

    async def _execute_single_tool(self, tc: Any, timeout_ms: int, retry_max: int, backoff_base_ms: int) -> tuple:
        """Execute a single tool with retries and timing."""
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

    async def _execute_tool_batch(self, tool_batch: List[Any], timeout_ms: int, retry_max: int, backoff_base_ms: int) -> List[tuple]:
        """Execute a batch of similar tools concurrently."""
        if not tool_batch:
            return []
        
        # Execute all tools in the batch concurrently
        batch_results = await asyncio.gather(*[
            self._execute_single_tool(tc, timeout_ms, retry_max, backoff_base_ms)
            for tc in tool_batch
        ])
        
        return batch_results

    async def _arun_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, role: str, max_iters: int | None = None) -> Any:
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
            
            last_response = await self._achat_once(messages, model, role)
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
            # Execute tool calls concurrently with bounded parallelism and batching
            rc = load_runtime_config(self.project_root)
            timeout_ms = int(rc.get("tools", {}).get("timeoutMs", 8000))
            parallelism = int(rc.get("tools", {}).get("parallelism", 4))
            retry_max = int(rc.get("tools", {}).get("retryMax", 2))
            backoff_base_ms = int(rc.get("tools", {}).get("backoffBaseMs", 200))

            # Group tool calls by type for potential batching
            tool_groups = self._group_tool_calls_for_batching(tool_calls)
            
            async def run_one_or_batch(tc_or_group):
                if isinstance(tc_or_group, list):
                    # Batch execution
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms)
                else:
                    # Single tool execution
                    return await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms)

            # Run with bounded concurrency
            sem = asyncio.Semaphore(parallelism)

            async def sem_wrapped(tc_or_group):
                async with sem:
                    return await run_one_or_batch(tc_or_group)

            # Execute all tools (single or batched) concurrently
            results = await asyncio.gather(*[sem_wrapped(tc_or_group) for tc_or_group in tool_groups])
            
            # Flatten results from batched executions
            flattened_results = []
            for result in results:
                if isinstance(result, list):
                    flattened_results.extend(result)
                else:
                    flattened_results.append(result)
            
            for tool_call_id, name, result, attempts, cache_hit in flattened_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(result),
                })
            # Finalization turn after tools: ask model to produce a user-facing reply
            final_resp = await self._achat_once(messages, model, role)
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
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        # Safely execute async flow whether or not an event loop is already running
        import asyncio
        try:
            # If there is a running loop (e.g., inside pytest-asyncio), run our coroutine in a new thread/loop
            asyncio.get_running_loop()

            result_holder: Dict[str, Any] = {}

            def _thread_runner():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    result_holder["resp"] = new_loop.run_until_complete(self._run_tools_loop(messages, model=model, role="smart"))
                finally:
                    new_loop.close()

            t = threading.Thread(target=_thread_runner, daemon=True)
            t.start()
            t.join()
            return result_holder["resp"]
        except RuntimeError:
            # No running loop in this thread, create one and run normally
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._run_tools_loop(messages, model=model, role="smart"))
            finally:
                loop.close()

    async def aconverse(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Async version of converse for non-blocking operations."""
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        return await self._arun_tools_loop(messages, model=model, role="smart")

    def recommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        # Use async version to avoid threading overhead
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, submit to the running loop
                fut = asyncio.run_coroutine_threadsafe(self._run_tools_loop(messages, model=model, role="smart"), loop)
                return fut.result()
            else:
                return loop.run_until_complete(self._run_tools_loop(messages, model=model, role="smart"))
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._run_tools_loop(messages, model=model, role="smart"))
            finally:
                loop.close()

    async def arecommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Async version of recommend for non-blocking operations."""
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        return await self._arun_tools_loop(messages, model=model, role="smart")


