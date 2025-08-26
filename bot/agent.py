from __future__ import annotations

from typing import Any, Dict, List, Callable, Optional
from pathlib import Path
import json
import asyncio
import logging
import threading

from llm.clients import LLMClient
from .agent_prompt import build_agent_system_prompt
from .tools.registry import build_openai_tools_and_registry
from .tools.tool_impl import build_preferences_context  # reuse the same formatter
from config.loader import load_runtime_config
from .tool_summarizers import summarize_tool_result
from .tools.result_cache import put_tool_result
from ux.progress import build_progress_broadcaster


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
        # Build async progress broadcaster (includes legacy callback sink and optional Discord sink)
        try:
            self.progress = build_progress_broadcaster(self.project_root, progress_callback)
        except Exception:
            self.progress = None  # Fallback; progress is best-effort

    async def _emit_progress(self, event: str, data: Any) -> None:
        try:
            if getattr(self, "progress", None) is not None:
                await self.progress.emit(event, data)
            elif self.progress_callback:
                # Legacy direct callback
                await asyncio.to_thread(self.progress_callback, event, str(data))
        except Exception:
            pass

    def _chat_once(self, messages: List[Dict[str, Any]], model: str, role: str, tool_choice_override: Optional[str] = None) -> Any:
        self.log.debug("LLM.chat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        # Pull optional reasoningEffort/params for role from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, role)
        params = dict(sel.get("params", {}))
        # gpt-5 family requires temperature exactly 1
        params["temperature"] = 1
        tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
        # Pass tool_choice via params only to avoid duplicate named arg binding
        params["tool_choice"] = tool_choice_value
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            reasoning=sel.get("reasoningEffort"),
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

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str, role: str, tool_choice_override: Optional[str] = None) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        self.log.debug("LLM.achat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        await self._emit_progress("llm.start", {"model": model, "messages": len(messages)})
        if getattr(self, "progress", None) is not None:
            try:
                await self.progress.typing_start("llm")
            except Exception:
                pass
        if hasattr(self.llm, "achat"):
            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, role)
            params = dict(sel.get("params", {}))
            params["temperature"] = 1
            tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
            params["tool_choice"] = tool_choice_value
            resp = await self.llm.achat(
                model=model,
                messages=messages,
                tools=self.openai_tools,
                reasoning=sel.get("reasoningEffort"),
                **params,
            )
        else:
            # Fallback: run sync client.chat in a thread to avoid blocking the event loop
            import functools
            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, role)
            params = dict(sel.get("params", {}))
            params["temperature"] = 1
            tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
            params["tool_choice"] = tool_choice_value
            fn = functools.partial(
                self.llm.chat,
                model=model,
                messages=messages,
                tools=self.openai_tools,
                reasoning=sel.get("reasoningEffort"),
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
        if getattr(self, "progress", None) is not None:
            try:
                await self.progress.typing_stop("llm")
            except Exception:
                pass
        await self._emit_progress("llm.finish", {"model": model, "content_preview": content_preview})
        return resp

    def _results_indicate_finalizable(self, tool_name_and_results: List[tuple]) -> bool:
        """Heuristic to decide if we likely have enough info to finalize.

        True when a write-style tool succeeded, or when we have any read-style
        content without errors. Conservative on errors.
        """
        try:
            any_error = False
            any_write_success = False
            any_read_content = False

            def _is_write_tool(name: str) -> bool:
                n = (name or "").lower()
                if any(x in n for x in ("add", "update", "delete", "monitor", "set_", "create", "remove")):
                    return True
                if n in ("update_household_preferences",):
                    return True
                return False

            def _has_nonempty_list(d: Dict[str, Any]) -> bool:
                for key in ("items", "results", "movies", "series", "episodes", "playlists", "collections"):
                    val = d.get(key)
                    if isinstance(val, list) and len(val) > 0:
                        return True
                return False

            for _tc_id, name, result, _attempts, _cache_hit in tool_name_and_results:
                if isinstance(result, dict):
                    if result.get("ok") is False or "error" in result:
                        any_error = True
                    if _is_write_tool(str(name)) and result.get("ok") is True and "error" not in result:
                        any_write_success = True
                    if _has_nonempty_list(result):
                        any_read_content = True
                else:
                    any_read_content = True

            if any_write_success:
                return True
            if any_error:
                return False
            return any_read_content
        except Exception:
            return False

    def _is_write_tool_name(self, name: str) -> bool:
        """Return True if the tool name likely performs a write/side-effect."""
        try:
            n = (name or "").lower()
            if ("add" in n) or ("update" in n) or ("delete" in n) or ("monitor" in n) or n.startswith("set_") or ("create" in n) or ("remove" in n) or (n in ("update_household_preferences",)):
                return True
        except Exception:
            pass
        return False

    def _contains_write_success(self, flat_results: List[tuple]) -> bool:
        """Detect if any write-style tool succeeded in the last batch."""
        try:
            for _tc_id, name, result, _attempts, _cache_hit in flat_results:
                if self._is_write_tool_name(str(name)) and isinstance(result, dict) and result.get("ok") is True and ("error" not in result):
                    return True
        except Exception:
            return False
        return False

    async def _run_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, role: str, max_iters: int | None = None, stream_final_to_callback: Optional[Callable[[str], Any]] = None) -> Any:
        # Load runtime config for loop controls
        rc = load_runtime_config(self.project_root)
        # Role-specific iteration limits: prefer agentMaxIters/workerMaxIters, fallback to legacy maxIters
        llm_cfg = rc.get("llm", {}) or {}
        if role in ("smart", "chat"):
            cfg_max_iters = int(llm_cfg.get("agentMaxIters", llm_cfg.get("maxIters", 4)))
        elif role == "worker":
            cfg_max_iters = int(llm_cfg.get("workerMaxIters", llm_cfg.get("maxIters", 3)))
        else:
            cfg_max_iters = int(llm_cfg.get("maxIters", 4))
        iters = max_iters or cfg_max_iters
        # System message + optional dynamic household preferences context (for recommendations)
        parallelism_for_prompt = int(rc.get("tools", {}).get("parallelism", 4))
        # Compute max iterations for this role to pass as a hint into the system prompt
        llm_cfg_for_iters = rc.get("llm", {}) or {}
        if role in ("smart", "chat"):
            cfg_max_iters = int(llm_cfg_for_iters.get("agentMaxIters", llm_cfg_for_iters.get("maxIters", 8)))
        elif role == "worker":
            cfg_max_iters = int(llm_cfg_for_iters.get("workerMaxIters", llm_cfg_for_iters.get("maxIters", 8)))
        else:
            cfg_max_iters = int(llm_cfg_for_iters.get("maxIters", 8))
        messages: List[Dict[str, Any]] = [{"role": "system", "content": build_agent_system_prompt(parallelism_for_prompt, cfg_max_iters)}]
        await self._emit_progress("agent.start", {"parallelism": parallelism_for_prompt, "iters": iters})
        try:
            if getattr(self, "progress", None) is not None:
                self.progress.start_heartbeat("agent")
        except Exception:
            pass
        
        # Check if we should add household preferences context
        # For OpenAI GPT-5 models or OpenRouter models that support reasoning
        should_add_prefs = (
            ("gpt-5" in str(model)) or 
            (hasattr(self.llm, 'provider') and self.llm.provider == "openrouter" and "glm-4.5" in str(model))
        )
        
        if should_add_prefs:
            try:
                prefs_path = self.project_root / "data" / "household_preferences.json"
                def _read_prefs():
                    with open(prefs_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                prefs = await asyncio.to_thread(_read_prefs)
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
        # Deduplicate identical tool calls within a run to reduce latency
        dedup_cache: Dict[str, Any] = {}
        last_response: Any = None
        force_finalize_next = False
        next_tool_choice_override: Optional[str] = None
        write_phase_allowed = False
        require_validation_read = False
        for iter_idx in range(iters):
            self.log.info(f"agent iteration {iter_idx+1}/{iters}")
            
            # Notify progress callback about LLM thinking
            await self._emit_progress("thinking", {"iteration": f"{iter_idx+1}/{iters}"})
            
            last_response = await self._achat_once(messages, model, role, tool_choice_override=next_tool_choice_override)
            next_tool_choice_override = None
            choice = last_response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                self.log.info("no tool calls; returning final answer")
                try:
                    if getattr(self, "progress", None) is not None:
                        self.progress.stop_heartbeat("agent")
                except Exception:
                    pass
                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                return last_response
            # Phase selection: read-only first, then writes; allow explicit validation reads after writes
            if require_validation_read:
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                if ro_calls:
                    tool_calls = ro_calls
                await self._emit_progress("phase.validation", {"iteration": f"{iter_idx+1}/{iters}"})
                messages.append({
                    "role": "system",
                    "content": "Validation step: perform read-only checks to confirm earlier writes. Do not perform write operations now."
                })
            elif not write_phase_allowed:
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                if ro_calls:
                    tool_calls = ro_calls
                    write_phase_allowed = True
                    await self._emit_progress("phase.read_only", {"iteration": f"{iter_idx+1}/{iters}"})
                    messages.append({
                        "role": "system",
                        "content": "Phase 1 (read-only): gather information and identify exact targets. Do not perform write operations yet."
                    })
                else:
                    write_phase_allowed = True
                    await self._emit_progress("phase.write_enabled", {"iteration": f"{iter_idx+1}/{iters}"})

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
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                else:
                    # Single tool execution
                    return await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)

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
            # Determine max items to keep in summaries and cache TTL
            list_max_items = int(rc.get("tools", {}).get("listMaxItems", 5))
            cache_ttl_sec = int(rc.get("cache", {}).get("ttlShortSec", 60))
            for tool_call_id, name, result, attempts, cache_hit in flattened_results:
                # Store raw result and attach ref_id for on-demand detail fetching
                ref_id = None
                try:
                    ref_id = put_tool_result(result, cache_ttl_sec)
                except Exception:
                    ref_id = None

                # Summarize and minify tool output before appending
                try:
                    # If result set is very small (<=2), preserve raw fields (truncated) instead of lossy summary
                    preserved = self._preserve_raw_if_small(result, max_keep=2)
                    summarized = preserved if preserved is not None else summarize_tool_result(name, result, max_items=list_max_items)
                except Exception:
                    summarized = result

                payload = {"ref_id": ref_id, "summary": summarized}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(payload, separators=(",", ":")),
                })
            # Post-write validation planning and finalize gating
            write_success = self._contains_write_success(flattened_results)
            if write_success and not require_validation_read:
                require_validation_read = True
                await self._emit_progress("phase.validation_planned", {"iteration": f"{iter_idx+1}/{iters}"})
            if require_validation_read and not write_success:
                # We were in validation mode this turn; validation done, proceed to finalize next
                require_validation_read = False
                messages.append({
                    "role": "system",
                    "content": "Validation complete. Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."
                })
                force_finalize_next = True
            else:
                try:
                    allowed_to_finalize = self._results_indicate_finalizable(flattened_results)
                    # Do not finalize immediately if a write just happened; require a validation read first
                    if write_success:
                        allowed_to_finalize = False
                    if allowed_to_finalize:
                        messages.append({
                            "role": "system",
                            "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."
                        })
                        if stream_final_to_callback is not None:
                            try:
                                from config.loader import resolve_llm_selection
                                _, sel = resolve_llm_selection(self.project_root, role)
                                params = dict(sel.get("params", {}))
                                params["temperature"] = 1
                                async for chunk in self.llm.astream_chat(
                                    model=model,
                                    messages=messages,
                                    tools=self.openai_tools,
                                    reasoning=sel.get("reasoningEffort"),
                                    tool_choice="none",
                                    **params,
                                ):
                                    try:
                                        await stream_final_to_callback(chunk)
                                    except Exception:
                                        pass
                                try:
                                    if getattr(self, "progress", None) is not None:
                                        self.progress.stop_heartbeat("agent")
                                except Exception:
                                    pass
                                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                                return await self._achat_once(messages, model, role, tool_choice_override="none")
                            except Exception:
                                force_finalize_next = True
                        else:
                            force_finalize_next = True
                    else:
                        force_finalize_next = False
                except Exception:
                    force_finalize_next = False
            if force_finalize_next:
                next_tool_choice_override = "none"
        # If we exhausted iterations and still have tool calls requested, synthesize a graceful reply
        synthesized = {
            "choices": [
                {
                    "message": {
                        "content": "Proceeding with best-effort result given the iteration limit."
                    }
                }
            ]
        }
        try:
            if getattr(self, "progress", None) is not None:
                self.progress.stop_heartbeat("agent")
        except Exception:
            pass
        await self._emit_progress("agent.finish", {"reason": "max_iters"})
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

    async def _execute_single_tool(self, tc: Any, timeout_ms: int, retry_max: int, backoff_base_ms: int, dedup_cache: Optional[Dict[str, Any]] = None) -> tuple:
        """Execute a single tool with retries and timing. Includes in-run de-duplication."""
        name = tc.function.name
        args_json = tc.function.arguments or "{}"
        self.log.info(f"tool call requested: {name}")
        self.log.debug("tool args", extra={"name": name, "args": args_json})
        
        # Emit tool start
        await self._emit_progress("tool.start", {"name": name, "args": args_json})
        
        # Parse args
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError as e:
            payload = {"ok": False, "error": "invalid_json", "details": str(e)}
            return tc.id, name, payload, 0, False

        # De-duplicate identical tool calls within the same run
        try:
            dedup_key = f"{name}:{json.dumps(args, sort_keys=True, separators=(',', ':'))}"
        except Exception:
            dedup_key = None
        if dedup_cache is not None and dedup_key is not None and dedup_key in dedup_cache:
            self.log.info("tool dedup cache hit", extra={"name": name})
            result = dedup_cache[dedup_key]
            # attempts=0 for dedup hit, cache_hit=True
            await self._emit_progress("tool.finish", {"name": name, "status": "ok", "duration_ms": 0, "attempts": 0, "cache_hit": True})
            return tc.id, name, result, 0, True

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
        # Store in dedup cache for subsequent identical calls
        if dedup_cache is not None and dedup_key is not None and status == "ok":
            dedup_cache[dedup_key] = result

        self.log.info("tool done", extra={"name": name, "status": status, "duration_ms": duration_ms, "attempts": attempt + 1, "cache_hit": cache_hit})
        await self._emit_progress("tool.finish" if status == "ok" else "tool.error", {"name": name, "status": status, "duration_ms": duration_ms, "attempts": attempt + 1})
        return tc.id, name, result, attempt + 1, cache_hit

    async def _execute_tool_batch(self, tool_batch: List[Any], timeout_ms: int, retry_max: int, backoff_base_ms: int, dedup_cache: Optional[Dict[str, Any]] = None) -> List[tuple]:
        """Execute a batch of similar tools concurrently."""
        if not tool_batch:
            return []
        
        # Execute all tools in the batch concurrently
        batch_results = await asyncio.gather(*[
            self._execute_single_tool(tc, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
            for tc in tool_batch
        ])
        
        return batch_results

    async def _arun_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, role: str, max_iters: int | None = None, stream_final_to_callback: Optional[Callable[[str], Any]] = None) -> Any:
        """Async version of _run_tools_loop for non-blocking operations."""
        # Load runtime config for loop controls
        rc = load_runtime_config(self.project_root)
        # Role-specific iteration limits: prefer agentMaxIters/workerMaxIters, fallback to legacy maxIters
        llm_cfg = rc.get("llm", {}) or {}
        if role in ("smart", "chat"):
            cfg_max_iters = int(llm_cfg.get("agentMaxIters", llm_cfg.get("maxIters", 4)))
        elif role == "worker":
            cfg_max_iters = int(llm_cfg.get("workerMaxIters", llm_cfg.get("maxIters", 3)))
        else:
            cfg_max_iters = int(llm_cfg.get("maxIters", 4))
        iters = max_iters or cfg_max_iters
        # System message + optional dynamic household preferences context (for recommendations)
        parallelism_for_prompt = int(rc.get("tools", {}).get("parallelism", 4))
        # Compute max iterations for this role to pass as a hint into the system prompt
        llm_cfg_for_iters = rc.get("llm", {}) or {}
        if role in ("smart", "chat"):
            cfg_max_iters = int(llm_cfg_for_iters.get("agentMaxIters", llm_cfg_for_iters.get("maxIters", 8)))
        elif role == "worker":
            cfg_max_iters = int(llm_cfg_for_iters.get("workerMaxIters", llm_cfg_for_iters.get("maxIters", 8)))
        else:
            cfg_max_iters = int(llm_cfg_for_iters.get("maxIters", 8))
        messages: List[Dict[str, Any]] = [{"role": "system", "content": build_agent_system_prompt(parallelism_for_prompt, cfg_max_iters)}]
        await self._emit_progress("agent.start", {"parallelism": parallelism_for_prompt, "iters": iters})
        try:
            if getattr(self, "progress", None) is not None:
                self.progress.start_heartbeat("agent")
        except Exception:
            pass
        
        # Check if we should add household preferences context
        # For OpenAI GPT-5 models or OpenRouter models that support reasoning
        should_add_prefs = (
            ("gpt-5" in str(model)) or 
            (hasattr(self.llm, 'provider') and self.llm.provider == "openrouter" and "glm-4.5" in str(model))
        )
        
        if should_add_prefs:
            try:
                prefs_path = self.project_root / "data" / "household_preferences.json"
                def _read_prefs():
                    with open(prefs_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                prefs = await asyncio.to_thread(_read_prefs)
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
        # Deduplicate identical tool calls within a run to reduce latency
        dedup_cache: Dict[str, Any] = {}
        last_response: Any = None
        force_finalize_next = False
        next_tool_choice_override: Optional[str] = None
        write_phase_allowed = False
        total_tool_calls = 0
        llm_calls_count = 0
        import time as _t
        t_loop_start = _t.monotonic()
        for iter_idx in range(iters):
            self.log.info(f"agent iteration {iter_idx+1}/{iters}")
            
            # Notify progress callback about LLM thinking
            await self._emit_progress("thinking", {"iteration": f"{iter_idx+1}/{iters}"})
            
            last_response = await self._achat_once(messages, model, role, tool_choice_override=next_tool_choice_override)
            llm_calls_count += 1
            next_tool_choice_override = None
            choice = last_response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, 'tool_calls', None)
            if not tool_calls:
                self.log.info("no tool calls; returning final answer")
                try:
                    if getattr(self, "progress", None) is not None:
                        self.progress.stop_heartbeat("agent")
                except Exception:
                    pass
                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                return last_response
            # Two-phase policy: first pass read-only, second pass allow writes
            def _is_write_tool_name(n: str) -> bool:
                n = (n or "").lower()
                return (
                    ("add" in n) or ("update" in n) or ("delete" in n) or ("monitor" in n) or n.startswith("set_") or ("create" in n) or ("remove" in n) or n in ("update_household_preferences",)
                )

            if not write_phase_allowed:
                ro_calls = [tc for tc in tool_calls if not _is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                if ro_calls:
                    tool_calls = ro_calls
                    messages.append({
                        "role": "system",
                        "content": "Phase 1 (read-only): gather information and identify exact targets. Do not perform write operations yet."
                    })
                    # Writes will be allowed next iteration
                    write_phase_allowed = True
                else:
                    # No read-only available; allow writes immediately to avoid stalling
                    write_phase_allowed = True

            # Append assistant message that contains ONLY the tool calls we will actually execute
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
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                else:
                    # Single tool execution
                    return await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)

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
            total_tool_calls += len(flattened_results)
            
            # Determine max items to keep in summaries and cache TTL
            list_max_items = int(rc.get("tools", {}).get("listMaxItems", 5))
            cache_ttl_sec = int(rc.get("cache", {}).get("ttlShortSec", 60))
            for tool_call_id, name, result, attempts, cache_hit in flattened_results:
                ref_id = None
                try:
                    ref_id = put_tool_result(result, cache_ttl_sec)
                except Exception:
                    ref_id = None

                try:
                    preserved = self._preserve_raw_if_small(result, max_keep=2)
                    summarized = preserved if preserved is not None else summarize_tool_result(name, result, max_items=list_max_items)
                except Exception:
                    summarized = result
                payload = {"ref_id": ref_id, "summary": summarized}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": json.dumps(payload, separators=(",", ":")),
                })
            # Consider early finalize after tool results; if forced, do a finalize-only turn immediately
            try:
                if self._results_indicate_finalizable(flattened_results):
                    messages.append({
                        "role": "system",
                        "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."
                    })
                    if stream_final_to_callback is not None:
                        try:
                            from config.loader import resolve_llm_selection
                            _, sel = resolve_llm_selection(self.project_root, role)
                            params = dict(sel.get("params", {}))
                            params["temperature"] = 1
                            async for chunk in self.llm.astream_chat(
                                model=model,
                                messages=messages,
                                tools=self.openai_tools,
                                reasoning=sel.get("reasoningEffort"),
                                tool_choice="none",
                                **params,
                            ):
                                try:
                                    await stream_final_to_callback(chunk)
                                except Exception:
                                    pass
                            try:
                                if getattr(self, "progress", None) is not None:
                                    self.progress.stop_heartbeat("agent")
                            except Exception:
                                pass
                            await self._emit_progress("agent.finish", {"reason": "final_answer"})
                            return await self._achat_once(messages, model, role, tool_choice_override="none")
                        except Exception:
                            force_finalize_next = True
                    else:
                        force_finalize_next = True
            except Exception:
                pass

        # Metrics
        try:
            elapsed_ms = int((_t.monotonic() - t_loop_start) * 1000)
            await self._emit_progress("agent.metrics", {"iters": iters, "llm_calls": llm_calls_count, "tool_calls": total_tool_calls, "elapsed_ms": elapsed_ms})
        except Exception:
            pass
        # If we exhausted iterations and still have tool calls requested, synthesize a graceful reply
        synthesized = {
            "choices": [
                {
                    "message": {
                        "content": "Proceeding with best-effort result given the iteration limit."
                    }
                }
            ]
        }
        try:
            if getattr(self, "progress", None) is not None:
                self.progress.stop_heartbeat("agent")
        except Exception:
            pass
        await self._emit_progress("agent.finish", {"reason": "max_iters"})
        return synthesized  # type: ignore[return-value]

    def _preserve_raw_if_small(self, result: Any, max_keep: int) -> Optional[Dict[str, Any]]:
        """If the tool result contains a small list (<= max_keep), return a copy preserving fields.

        Checks common list keys and returns a truncated raw copy to avoid lossy summarization
        when there are very few items.
        """
        try:
            if not isinstance(result, dict):
                return None
            for key in ("items", "results", "movies", "series", "episodes", "playlists", "collections"):
                val = result.get(key)
                if isinstance(val, list) and len(val) <= max_keep:
                    out = dict(result)
                    out[key] = val[:max_keep]
                    return out
        except Exception:
            return None
        return None

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

    async def aconverse(self, messages: List[Dict[str, str]], stream_final_to_callback: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
        """Async version of converse for non-blocking operations."""
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        return await self._arun_tools_loop(messages, model=model, role="smart", max_iters=None)

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


