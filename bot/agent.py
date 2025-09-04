from __future__ import annotations

from typing import Any, Dict, List, Callable, Optional
from pathlib import Path
import json
import asyncio
import logging
import threading
import time

from llm.clients import LLMClient
from .agent_prompt import build_agent_system_prompt
from .tools.registry_cache import get_cached_registry
from .tools.tool_impl import build_preferences_context  # reuse the same formatter
from config.loader import load_runtime_config
from .tool_summarizers import summarize_tool_result
from .tools.result_cache import put_tool_result
from ux.progress import build_progress_broadcaster
from integrations.ttl_cache import shared_cache


class Agent:
    def __init__(self, *, api_key: str, project_root: Path, provider: str = "openai", progress_callback: Optional[Callable[[str, str], None]] = None):
        # Override provider by config priority if available
        from config.loader import resolve_llm_selection, load_settings
        prov, _sel = resolve_llm_selection(project_root, "chat", load_settings(project_root))
        self.llm = LLMClient(api_key, provider=prov)
        self.openai_tools, self.tool_registry = get_cached_registry(self.llm)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.agent")
        self.progress_callback = progress_callback
        # Build async progress broadcaster (includes legacy callback sink and optional Discord sink)
        try:
            self.progress = build_progress_broadcaster(self.project_root, progress_callback)
        except Exception:
            self.progress = None  # Fallback; progress is best-effort
        # Per-instance caches/state
        self._role_selection_cache: Dict[str, Dict[str, Any]] = {}
        self._circuit: Dict[str, Dict[str, Any]] = {}
        self._tuning_cfg: Dict[str, Any] = {}

    def _get_role_selection(self, role: str) -> Dict[str, Any]:
        """Resolve and cache LLM selection for a role for this Agent instance."""
        if role in self._role_selection_cache:
            return self._role_selection_cache[role]
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, role)
        self._role_selection_cache[role] = sel
        return sel

    def _classify_tool_family(self, name: str) -> str:
        n = (name or "").lower()
        if n.startswith("tmdb_"):
            return "tmdb"
        if n.startswith("plex_"):
            return "plex"
        if n.startswith("radarr_"):
            return "radarr"
        if n.startswith("sonarr_"):
            return "sonarr"
        return "other"

    def _select_tool_tuning(self, name: str) -> Dict[str, int]:
        """Pick timeout/retry/backoff/hedge delay using per-tool or per-family overrides."""
        tools_cfg = self._tuning_cfg.get("tools", {}) or self._tuning_cfg.get("tools_cfg", {}) or {}
        family = self._classify_tool_family(name)
        default_timeout = int(tools_cfg.get("timeoutMs", 8000))
        default_retry = int(tools_cfg.get("retryMax", 2))
        default_backoff = int(tools_cfg.get("backoffBaseMs", 200))
        hedge_by_family = (tools_cfg.get("hedgeDelayMsByFamily", {}) or {})
        per_tool = (tools_cfg.get("perTool", {}) or {})
        per_family = (tools_cfg.get("perFamily", {}) or {})
        cfg = {
            "timeoutMs": int(per_tool.get(name, {}).get("timeoutMs", per_family.get(family, {}).get("timeoutMs", default_timeout))),
            "retryMax": int(per_tool.get(name, {}).get("retryMax", per_family.get(family, {}).get("retryMax", default_retry))),
            "backoffBaseMs": int(per_tool.get(name, {}).get("backoffBaseMs", per_family.get(family, {}).get("backoffBaseMs", default_backoff))),
            "hedgeDelayMs": int(hedge_by_family.get(family, 0)),
        }
        return cfg

    def _select_parallelism_for_family(self, family: str) -> int:
        tools_cfg = self._tuning_cfg.get("tools", {}) or self._tuning_cfg.get("tools_cfg", {}) or {}
        default_parallelism = int(tools_cfg.get("parallelism", 4))
        family_parallelism = (tools_cfg.get("familyParallelism", {}) or {})
        return int(family_parallelism.get(family, default_parallelism))

    def _normalize_args_for_dedup(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize common query-like args so near-duplicates dedup nicely."""
        try:
            out = dict(args)
            for key in ("query", "q", "title", "name"):
                if key in out and isinstance(out[key], str):
                    out[key] = out[key].strip().lower()
            return out
        except Exception:
            return args

    def _repair_json(self, s: str) -> Optional[Dict[str, Any]]:
        """Attempt a quick, safe repair of slightly malformed JSON tool args."""
        try:
            return json.loads(s)
        except Exception:
            pass
        try:
            fixed = s.strip()
            # Replace single quotes with double quotes if appears to be JSON-ish
            if fixed and fixed[0] in "{'\"":
                fixed = fixed.replace("'", '"')
            # Remove trailing commas before } or ]
            fixed = fixed.replace(",\n}", "\n}").replace(",}\n", "}\n").replace(", ]", "]")
            return json.loads(fixed)
        except Exception:
            return None

    def _prune_old_tool_messages(self, messages: List[Dict[str, Any]], max_tool_messages: int) -> None:
        """Keep only the most recent N tool messages to control context growth."""
        try:
            indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
            if len(indices) <= max_tool_messages:
                return
            # Remove oldest tool messages beyond the cap
            to_remove = indices[: len(indices) - max_tool_messages]
            removed_count = len(to_remove)
            for idx in reversed(to_remove):
                messages.pop(idx)
            messages.append({
                "role": "system",
                "content": f"Older tool outputs pruned to reduce context. Pruned_count={removed_count}."
            })
        except Exception:
            return

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
        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug("LLM.chat start", extra={
                "model": model,
                "message_count": len(messages),
            })
        # Pull optional reasoningEffort/params for role from config
        sel = self._get_role_selection(role)
        params = dict(sel.get("params", {}))
        # gpt-5 family requires temperature exactly 1
        params["temperature"] = 1
        tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
        # Decide tools to send and only include tool_choice when tools are present
        tools_to_send = None if tool_choice_value == "none" else self.openai_tools
        if tools_to_send is not None:
            params["tool_choice"] = tool_choice_value
        else:
            # Ensure we do not send tool_choice without tools
            params.pop("tool_choice", None)
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=tools_to_send,
            reasoning=sel.get("reasoningEffort"),
            **params,
        )

        try:
            content_preview = (resp.choices[0].message.content or "")[:120]  # type: ignore[attr-defined]
        except Exception:
            content_preview = "<no content>"
        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug("LLM.chat done", extra={
                "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),  # type: ignore[attr-defined]
                "content_preview": content_preview,
            })
        return resp

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str, role: str, tool_choice_override: Optional[str] = None) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        if self.log.isEnabledFor(logging.DEBUG):
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
            sel = self._get_role_selection(role)
            params = dict(sel.get("params", {}))
            params["temperature"] = 1
            tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
            tools_to_send = None if tool_choice_value == "none" else self.openai_tools
            if tools_to_send is not None:
                params["tool_choice"] = tool_choice_value
            else:
                params.pop("tool_choice", None)
            resp = await self.llm.achat(
                model=model,
                messages=messages,
                tools=tools_to_send,
                reasoning=sel.get("reasoningEffort"),
                **params,
            )
        else:
            # Fallback: run sync client.chat in a thread to avoid blocking the event loop
            import functools
            sel = self._get_role_selection(role)
            params = dict(sel.get("params", {}))
            params["temperature"] = 1
            tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
            tools_to_send = None if tool_choice_value == "none" else self.openai_tools
            if tools_to_send is not None:
                params["tool_choice"] = tool_choice_value
            else:
                params.pop("tool_choice", None)
            fn = functools.partial(
                self.llm.chat,
                model=model,
                messages=messages,
                tools=tools_to_send,
                reasoning=sel.get("reasoningEffort"),
                **params,
            )
            resp = await asyncio.to_thread(fn)

        try:
            content_preview = (resp.choices[0].message.content or "")[:120]  # type: ignore[attr-defined]
        except Exception:
            content_preview = "<no content>"
        if self.log.isEnabledFor(logging.DEBUG):
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
                    # Treat write success broadly: any write tool that returns a dict without an explicit error
                    # and without ok=False is considered successful. Many integrations return raw objects (e.g., {"id": 123}).
                    if _is_write_tool(str(name)) and ("error" not in result) and (result.get("ok") is not False):
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

    def _is_circuit_open(self, tool_name: str) -> bool:
        """Check if the circuit breaker is open for a specific tool."""
        try:
            circuit_config = self._tuning_cfg.get("tools_cfg", {}).get("circuit", {})
            open_after_failures = circuit_config.get("openAfterFailures", 3)
            open_for_ms = circuit_config.get("openForMs", 3000)
            
            if tool_name not in self._circuit:
                return False
            
            circuit_state = self._circuit[tool_name]
            failure_count = circuit_state.get("failures", 0)
            last_failure_time = circuit_state.get("last_failure", 0)
            
            if failure_count >= open_after_failures:
                # Check if enough time has passed to reset the circuit
                import time
                current_time = time.time() * 1000  # Convert to milliseconds
                if current_time - last_failure_time > open_for_ms:
                    # Reset circuit
                    self._circuit[tool_name] = {"failures": 0, "last_failure": 0}
                    return False
                return True
            
            return False
        except Exception:
            return False

    def _record_circuit_failure(self, tool_name: str) -> None:
        """Record a failure for circuit breaker tracking."""
        try:
            import time
            current_time = time.time() * 1000  # Convert to milliseconds
            
            if tool_name not in self._circuit:
                self._circuit[tool_name] = {"failures": 0, "last_failure": 0}
            
            self._circuit[tool_name]["failures"] += 1
            self._circuit[tool_name]["last_failure"] = current_time
        except Exception:
            pass

    def _record_circuit_success(self, tool_name: str) -> None:
        """Record a success to reset circuit breaker for a tool."""
        try:
            if tool_name in self._circuit:
                self._circuit[tool_name] = {"failures": 0, "last_failure": 0}
        except Exception:
            pass

    def _classify_error_retryability(self, error: Exception) -> str:
        """Classify errors as retryable, non_retryable, or circuit_breaker."""
        try:
            error_str = str(error).lower()
            
            # Non-retryable errors (permanent failures)
            if any(x in error_str for x in [
                "401", "unauthorized", "authentication", "invalid api key",
                "403", "forbidden", "permission denied", "access denied",
                "404", "not found", "does not exist",
                "400", "bad request", "validation", "invalid parameter",
                "movie already exists", "series already exists", "already been added"
            ]):
                return "non_retryable"
            
            # Circuit breaker triggers (rate limits, service overload)
            if any(x in error_str for x in [
                "429", "rate limit", "too many requests", "quota exceeded",
                "503", "service unavailable", "server overloaded",
                "502", "bad gateway", "upstream error"
            ]):
                return "circuit_breaker"
            
            # Retryable errors (temporary failures)
            if any(x in error_str for x in [
                "timeout", "connection", "network", "dns",
                "500", "internal server error", "temporary"
            ]):
                return "retryable"
            
            # Default to retryable for unknown errors
            return "retryable"
        except Exception:
            return "retryable"

    def _contains_write_success(self, flat_results: List[tuple]) -> bool:
        """Detect if any write-style tool succeeded in the last batch."""
        try:
            for _tc_id, name, result, _attempts, _cache_hit in flat_results:
                # Consider any write tool that returns a dict without an explicit error and not ok=False a success
                if self._is_write_tool_name(str(name)) and isinstance(result, dict) and ("error" not in result) and (result.get("ok") is not False):
                    return True
        except Exception:
            return False
        return False

    def _contains_write_failure(self, flat_results: List[tuple]) -> bool:
        """Detect if any write-style tool explicitly failed in the last batch."""
        try:
            for _tc_id, name, result, _attempts, _cache_hit in flat_results:
                if self._is_write_tool_name(str(name)) and isinstance(result, dict):
                    if (result.get("ok") is False) or ("error" in result):
                        return True
        except Exception:
            return False
        return False

    async def _run_tools_loop(self, base_messages: List[Dict[str, Any]], model: str, role: str, max_iters: int | None = None, stream_final_to_callback: Optional[Callable[[str], Any]] = None) -> Any:
        # Sync pathway removed: delegate to async loop for a single implementation.
        return await self._arun_tools_loop(base_messages, model, role, max_iters=max_iters, stream_final_to_callback=stream_final_to_callback)
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
        # Infer if user intent requires a write (e.g., add/update/delete/monitor)
        def _user_intent_requires_write(msgs: List[Dict[str, Any]]) -> bool:
            try:
                text_parts: List[str] = [str(m.get("content", "")) for m in msgs if m.get("role") == "user"]
                text = "\n".join(text_parts).lower()
                if not text.strip():
                    return False
                write_verbs = ("add", "delete", "remove", "update", "monitor", "set ")
                targets = ("radarr", "sonarr", "rating", "watchlist", "queue")
                if any(w in text for w in write_verbs) and any(t in text for t in targets):
                    return True
                # Common phrasing: "to my radarr" / "into radarr"
                if "to my radarr" in text or "to radarr" in text or "into radarr" in text:
                    return True
            except Exception:
                pass
            return False
        must_write = _user_intent_requires_write(base_messages)
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
        # If write is required by intent, make it explicit up front
        if must_write:
            messages.append({
                "role": "system",
                "content": (
                    "User intent requires a write operation. You MUST call the appropriate write tool to satisfy the request "
                    "before finalizing. For movies, prefer: identify TMDb id (tmdb_search/tmdb_movie_details or radarr_lookup), "
                    "then call radarr_add_movie with quality_profile_id and root_folder_path (discover via radarr_quality_profiles and radarr_root_folders if needed). "
                    "After the write, perform one quick read-only validation (e.g., radarr_get_movies) and then finalize. Do not claim success without performing the write."
                )
            })
        messages += base_messages
        # Deduplicate identical tool calls within a run to reduce latency
        dedup_cache: Dict[str, Any] = {}
        # Per-run tuning snapshot
        self._tuning_cfg = {
            "tools": rc.get("tools", {}) or {},
            "tools_cfg": rc.get("tools", {}) or {},
            "cache_ttl_short": int(rc.get("cache", {}).get("ttlShortSec", 60)),
            "cache_ttl_medium": int(rc.get("cache", {}).get("ttlMediumSec", rc.get("cache", {}).get("ttlShortSec", 60))),
            "list_max_default": int((rc.get("tools", {}) or {}).get("listMaxItems", 5)),
            "max_tool_msgs": int((rc.get("tools", {}) or {}).get("maxToolMessagesInContext", 12)),
        }
        last_response: Any = None
        force_finalize_next = False
        next_tool_choice_override: Optional[str] = None
        write_phase_allowed = False
        require_validation_read = False
        seen_write_intent = False
        write_completed = False
        write_failed_once = False
        allow_finalize_on_failure = False
        validation_done = False
        last_added_tmdb_id: Optional[int] = None
        last_added_title: Optional[str] = None
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
                # If user intent requires a write, force a tools turn instead of finalizing
                if must_write and not require_validation_read and not write_completed:
                    messages.append({
                        "role": "system",
                        "content": (
                            "Tool use required to satisfy the request. Call the necessary tool(s) now to perform the write. "
                            "Do not produce a final answer yet."
                        )
                    })
                    next_tool_choice_override = "required"
                    continue
                self.log.info("no tool calls; returning final answer")
                try:
                    if getattr(self, "progress", None) is not None:
                        self.progress.stop_heartbeat("agent")
                except Exception:
                    pass
                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                return last_response
            # Track if the LLM has expressed an intent to perform a write this turn
            try:
                if tool_calls:
                    if any(self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', '')) for tc in tool_calls):
                        seen_write_intent = True
            except Exception:
                pass

            # Phase selection: read-only first, then writes; after a write, enforce read-only validation only
            validation_planned_this_iter = False
            if require_validation_read or (write_completed and not validation_done):
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                # Allow parallel validation calls for better performance
                tool_calls = ro_calls
                await self._emit_progress("phase.validation", {"iteration": f"{iter_idx+1}/{iters}"})
                messages.append({
                    "role": "system",
                    "content": "Validation step: run quick read-only checks (e.g., fetch the item/list) to confirm the write succeeded. You may run multiple validation calls in parallel. Do not perform any write operations. Then finalize."
                })
                if tool_calls:
                    validation_planned_this_iter = True
            elif not write_phase_allowed:
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                if ro_calls:
                    tool_calls = ro_calls
                    write_phase_allowed = True
                    await self._emit_progress("phase.read_only", {"iteration": f"{iter_idx+1}/{iters}"})
                    # Make the two-phase policy explicit to the model
                    messages.append({
                        "role": "system",
                        "content": "Phase 1 (read-only): gather information and identify exact targets. Do not perform writes yet. Next, you may perform the necessary write."
                    })
                else:
                    write_phase_allowed = True
                    await self._emit_progress("phase.write_enabled", {"iteration": f"{iter_idx+1}/{iters}"})
                    messages.append({
                        "role": "system",
                        "content": "Phase 2 (write): proceed to perform the necessary write operation now based on identified targets. Avoid additional discovery first unless strictly required."
                    })

            # Append assistant message that contains tool calls
            messages.append({
                "role": "assistant",
                # Do not echo planning text back to the model on tool-call turns
                "content": "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            # Group tool calls by type for potential batching
            tool_groups = self._group_tool_calls_for_batching(tool_calls)
            
            async def run_one_or_batch(tc_or_group):
                if isinstance(tc_or_group, list):
                    # Batch execution
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                else:
                    # Single tool execution
                    return await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)

            # Default tuning values from config snapshot
            cfg_tools = self._tuning_cfg.get("tools_cfg", {}) or {}
            timeout_ms = int(cfg_tools.get("timeoutMs", 8000))
            retry_max = int(cfg_tools.get("retryMax", 2))
            backoff_base_ms = int(cfg_tools.get("backoffBaseMs", 200))

            # Execute all tools (single or batched) concurrently (per-batch limits applied inside)
            results = await asyncio.gather(*[run_one_or_batch(tc_or_group) for tc_or_group in tool_groups])
            
            # Flatten results from batched executions
            flattened_results = []
            for result in results:
                if isinstance(result, list):
                    flattened_results.extend(result)
                else:
                    flattened_results.append(result)
            
            # Process results asynchronously for better performance
            processed_messages = await self._process_results_async(flattened_results)
            messages.extend(processed_messages)
            
            # Track last write attempt details for validation matching
            for tool_call_id, name, result, attempts, cache_hit in flattened_results:
                try:
                    if self._is_write_tool_name(str(name)) and isinstance(result, dict):
                        if "radarr_add_movie" in str(name):
                            # Try common shapes
                            last_added_tmdb_id = (
                                result.get("tmdbId") or result.get("tmdb_id") or result.get("tmdbid") or
                                (result.get("movie", {}) or {}).get("tmdbId")
                            )
                            t = result.get("title") or (result.get("movie", {}) or {}).get("title")
                            last_added_title = str(t) if t else last_added_title
                except Exception:
                    pass
            # Prune older tool messages to keep context small
            self._prune_old_tool_messages(messages, int(self._tuning_cfg.get("max_tool_msgs", 12)))
            # Post-write validation planning and finalize gating
            write_success = self._contains_write_success(flattened_results)
            if write_success:
                write_completed = True
            if write_success and not require_validation_read and not validation_done:
                require_validation_read = True
                await self._emit_progress("phase.validation_planned", {"iteration": f"{iter_idx+1}/{iters}"})
                # Instruct the model that a quick read-only validation comes next
                messages.append({
                    "role": "system",
                    "content": "Write completed. Now perform a quick read-only validation (e.g., fetch the created/updated item) and then finalize. Do not perform any additional writes."
                })
            # If we executed a validation read this turn, decide to finalize next turn
            if validation_planned_this_iter:
                require_validation_read = False
                validation_done = True
                # Heuristic validation success: try to find the added item in lists
                validation_success = None
                try:
                    def _iter_lists(d: Dict[str, Any]):
                        for key in ("items", "results", "movies", "series", "episodes", "playlists", "collections"):
                            val = d.get(key)
                            if isinstance(val, list):
                                for it in val:
                                    yield it
                    found = False
                    for _tc_id, _n, res, _att, _ch in flattened_results:
                        if isinstance(res, dict):
                            for it in _iter_lists(res):
                                try:
                                    tmdb_match = (last_added_tmdb_id is not None) and (int(it.get("tmdbId") or it.get("tmdb_id") or -1) == int(last_added_tmdb_id))
                                except Exception:
                                    tmdb_match = False
                                title_match = False
                                try:
                                    if last_added_title:
                                        title_match = str(it.get("title") or "").strip().lower() == str(last_added_title).strip().lower()
                                except Exception:
                                    title_match = False
                                if tmdb_match or title_match:
                                    found = True
                                    break
                    validation_success = found
                except Exception:
                    validation_success = None
                if validation_success is False:
                    # Allow one more iteration to correct; do not force finalize yet
                    messages.append({
                        "role": "system",
                        "content": "It looks like the action might not have completed as expected. You can try one more time or let me know if you need help, then I'll wrap up with what we have."
                    })
                    force_finalize_next = False
                else:
                    messages.append({
                        "role": "system",
                        "content": "Validation complete. Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools."
                    })
                    force_finalize_next = True
            else:
                try:
                    allowed_to_finalize = self._results_indicate_finalizable(flattened_results)
                    # Do not finalize immediately if a write just happened; require a validation read first
                    if write_success:
                        allowed_to_finalize = False
                    # If the model has already signaled write intent at any point, do not finalize until a write succeeds
                    if seen_write_intent and not write_success:
                        allowed_to_finalize = False
                    # If user intent requires a write, do not finalize until a write succeeds
                    if must_write and not write_success:
                        allowed_to_finalize = False
                    if allowed_to_finalize:
                        messages.append({
                            "role": "system",
                            "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools."
                        })
                        if stream_final_to_callback is not None:
                            try:
                                sel = self._get_role_selection(role)
                                params = dict(sel.get("params", {}))
                                params["temperature"] = 1
                                final_text_parts: List[str] = []
                                async for chunk in self.llm.astream_chat(
                                    model=model,
                                    messages=messages,
                                    tools=None,
                                    reasoning=sel.get("reasoningEffort"),
                                    **params,
                                ):
                                    try:
                                        final_text_parts.append(chunk)
                                        await stream_final_to_callback(chunk)
                                    except Exception:
                                        pass
                                try:
                                    if getattr(self, "progress", None) is not None:
                                        self.progress.stop_heartbeat("agent")
                                except Exception:
                                    pass
                                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                                final_text = "".join(final_text_parts) if final_text_parts else ""
                                return {
                                    "choices": [
                                        {
                                            "message": {"content": final_text}
                                        }
                                    ]
                                }
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
        # Determine the likely reason for hitting the iteration limit
        reason = "processing your request"
        if must_write and not write_completed:
            reason = "trying to complete the requested action"
        elif seen_write_intent and not write_completed:
            reason = "attempting to perform the requested operation"
        elif require_validation_read and not validation_done:
            reason = "validating the completed action"
        elif write_completed and not validation_done:
            reason = "confirming the action was successful"
        
        synthesized = {
            "choices": [
                {
                    "message": {
                        "content": f"I hit my processing limit while {reason}, but here's what I found with the time available!"
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
        """Enhanced batching strategy with smart grouping and performance optimization.
        
        This method implements intelligent batching based on:
        1. Tool family characteristics (TMDb is fast, *arr is slower)
        2. Operation type (reads vs writes)
        3. Optimal batch sizes per family
        4. Cross-family batching opportunities
        
        Returns a list where each element is either a single tool call or a list of tool calls
        that can be executed as a batch.
        """
        if not tool_calls:
            return []
        
        # Categorize tools by family and operation type
        fast_tools = []      # TMDb, quick Plex operations
        medium_tools = []    # Plex searches, *arr reads
        slow_tools = []      # *arr writes, complex operations
        write_tools = []     # Any write operations
        
        for tc in tool_calls:
            name = tc.function.name
            family = self._classify_tool_family(name)
            
            # Categorize by performance characteristics
            if family == "tmdb":
                fast_tools.append(tc)
            elif family == "plex":
                if any(op in name for op in ["search", "get_", "recently_added", "on_deck"]):
                    fast_tools.append(tc)
                else:
                    medium_tools.append(tc)
            elif family in ["radarr", "sonarr"]:
                if "get_" in name or "system_status" in name:
                    medium_tools.append(tc)
                else:
                    slow_tools.append(tc)
            else:
                medium_tools.append(tc)
            
            # Track write operations separately
            if self._is_write_tool_name(name):
                write_tools.append(tc)
        
        # Create optimized batches
        result = []
        
        # Batch fast tools aggressively (up to 8 per batch)
        if fast_tools:
            for i in range(0, len(fast_tools), 8):
                batch = fast_tools[i:i+8]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Batch medium tools moderately (up to 4 per batch)
        if medium_tools:
            for i in range(0, len(medium_tools), 4):
                batch = medium_tools[i:i+4]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Keep slow tools individual or small batches (up to 2 per batch)
        if slow_tools:
            for i in range(0, len(slow_tools), 2):
                batch = slow_tools[i:i+2]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Special handling for write operations - keep them separate for safety
        if write_tools:
            # Remove write tools from other batches and add them individually
            result = [batch for batch in result if not any(self._is_write_tool_name(tc.function.name) for tc in (batch if isinstance(batch, list) else [batch]))]
            result.extend(write_tools)
        
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
        """Execute a single tool with retries and timing. Includes in-run de-duplication.

        Note: This signature is kept for backward-compat with existing call sites but internal tuning may override these values.
        """
        name = tc.function.name
        args_json = tc.function.arguments or "{}"
        self.log.info(f"tool call requested: {name}")
        self.log.debug("tool args", extra={"name": name, "args": args_json})
        
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

        # Emit tool start only for actual executions (not dedup hits)
        await self._emit_progress("tool.start", {"name": name, "args": args_json})

        # Execute with retries/backoff, timeout, and timing
        attempt = 0
        start = time.monotonic()
        cache_hit = False
        last_err = None
        tuning = self._select_tool_tuning(name)
        timeout_ms = int(tuning.get("timeoutMs", timeout_ms))
        retry_max = int(tuning.get("retryMax", retry_max))
        backoff_base_ms = int(tuning.get("backoffBaseMs", backoff_base_ms))
        hedge_delay_ms = int(tuning.get("hedgeDelayMs", 0))

        async def attempt_once():
            try:
                return await asyncio.wait_for(self.tool_registry.get(name)(args), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError as e:
                raise e

        while True:
            # Check circuit breaker before attempting
            if self._is_circuit_open(name):
                last_err = {"ok": False, "error": "circuit_breaker_open", "name": name, "message": "Circuit breaker is open for this tool"}
                result = last_err
                status = "error"
                break
                
            try:
                # Hedged attempt for read-only TMDB-like tools
                is_read_only = not self._is_write_tool_name(name)
                if hedge_delay_ms > 0 and is_read_only and self._classify_tool_family(name) == "tmdb":
                    primary = asyncio.create_task(attempt_once())
                    try:
                        await asyncio.wait_for(asyncio.shield(primary), timeout=hedge_delay_ms / 1000)
                        result = await primary
                    except asyncio.TimeoutError:
                        secondary = asyncio.create_task(attempt_once())
                        done, pending = await asyncio.wait({primary, secondary}, return_when=asyncio.FIRST_COMPLETED)
                        task = done.pop()
                        result = task.result()
                        for p in pending:
                            p.cancel()
                else:
                    result = await attempt_once()
                status = "ok"
                # Record success to reset circuit breaker
                self._record_circuit_success(name)
                break
            except asyncio.TimeoutError as e:
                last_err = {"ok": False, "error": "timeout", "timeout_ms": timeout_ms, "name": name}
                error_classification = "retryable"  # Timeouts are retryable
            except Exception as e:
                last_err = {"ok": False, "error": str(e)}
                error_classification = self._classify_error_retryability(e)
            
            # Record failure for circuit breaker
            self._record_circuit_failure(name)
            
            # Check if we should retry based on error classification
            if error_classification == "non_retryable":
                result = last_err
                status = "error"
                break
            elif error_classification == "circuit_breaker":
                # For circuit breaker errors, don't retry immediately
                result = last_err
                status = "error"
                break
            
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
        """Execute a batch of similar tools concurrently with enhanced parallelism control."""
        if not tool_batch:
            return []
        
        # Enhanced parallelism control based on tool characteristics
        first = tool_batch[0]
        fam = self._classify_tool_family(first.function.name)
        
        # Dynamic parallelism based on family and batch size
        if fam == "tmdb":
            # TMDb is fast, allow higher parallelism
            max_parallelism = min(len(tool_batch), 16)
        elif fam == "plex":
            # Plex is moderate, use family setting
            max_parallelism = self._select_parallelism_for_family(fam)
            max_parallelism = min(max_parallelism, len(tool_batch))
        elif fam in ["radarr", "sonarr"]:
            # *arr tools are slower, be more conservative
            max_parallelism = min(self._select_parallelism_for_family(fam), len(tool_batch), 4)
        else:
            max_parallelism = min(self._select_parallelism_for_family(fam), len(tool_batch))
        
        if max_parallelism <= 0:
            max_parallelism = len(tool_batch)
        
        sem = asyncio.Semaphore(max_parallelism)

        async def _sem_wrap(one):
            async with sem:
                return await self._execute_single_tool(one, timeout_ms, retry_max, backoff_base_ms, dedup_cache)

        # Execute with enhanced error handling and progress tracking
        try:
            batch_results = await asyncio.gather(*[_sem_wrap(tc) for tc in tool_batch], return_exceptions=True)
            
            # Handle any exceptions in batch results
            processed_results = []
            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    # Convert exception to error result tuple
                    tool_call = tool_batch[i]
                    error_result = (tool_call.id, tool_call.function.name, {"error": str(result)}, 1, False)
                    processed_results.append(error_result)
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            # Fallback: execute tools individually if batch fails
            self.log.warning(f"Batch execution failed, falling back to individual execution: {e}")
            individual_results = []
            for tc in tool_batch:
                try:
                    result = await self._execute_single_tool(tc, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                    individual_results.append(result)
                except Exception as individual_error:
                    error_result = (tc.id, tc.function.name, {"error": str(individual_error)}, 1, False)
                    individual_results.append(error_result)
            return individual_results

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
        # Infer if user intent requires a write
        def _user_intent_requires_write(msgs: List[Dict[str, Any]]) -> bool:
            try:
                text_parts: List[str] = [str(m.get("content", "")) for m in msgs if m.get("role") == "user"]
                text = "\n".join(text_parts).lower()
                if not text.strip():
                    return False
                write_verbs = ("add", "delete", "remove", "update", "monitor", "set ")
                targets = ("radarr", "sonarr", "rating", "watchlist", "queue")
                if any(w in text for w in write_verbs) and any(t in text for t in targets):
                    return True
                if "to my radarr" in text or "to radarr" in text or "into radarr" in text:
                    return True
                # Bare 'add <title>' implies adding media
                if "add" in text and not any(x in text for x in ("rating", "stars", "review", "note")):
                    return True
            except Exception:
                pass
            return False
        must_write = _user_intent_requires_write(base_messages)
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
        if must_write:
            messages.append({
                "role": "system",
                "content": (
                    "User intent requires a write operation. You MUST call the appropriate write tool to satisfy the request "
                    "before finalizing. For movies, prefer: identify TMDb id (tmdb_search/tmdb_movie_details or radarr_lookup), "
                    "then call radarr_add_movie with quality_profile_id and root_folder_path (discover via radarr_quality_profiles and radarr_root_folders if needed). "
                    "After the write, perform one quick read-only validation (e.g., radarr_get_movies) and then finalize. Do not claim success without performing the write."
                )
            })
        messages += base_messages
        # Deduplicate identical tool calls within a run to reduce latency
        dedup_cache: Dict[str, Any] = {}
        last_response: Any = None
        force_finalize_next = False
        next_tool_choice_override: Optional[str] = None
        write_phase_allowed = False
        require_validation_read = False
        seen_write_intent = False
        write_completed = False
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
                if must_write and (not write_completed) and (not require_validation_read):
                    messages.append({
                        "role": "system",
                        "content": (
                            "Tool use required to satisfy the request. Call the necessary tool(s) now to perform the write. "
                            "Do not produce a final answer yet."
                        )
                    })
                    next_tool_choice_override = "required"
                    continue
                self.log.info("no tool calls; returning final answer")
                try:
                    if getattr(self, "progress", None) is not None:
                        self.progress.stop_heartbeat("agent")
                except Exception:
                    pass
                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                return last_response
            # Track write intent signaled by the model
            try:
                if tool_calls:
                    if any(self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', '')) for tc in tool_calls):
                        seen_write_intent = True
            except Exception:
                pass

            # Two-phase policy with explicit validation stage (strict: block further writes after first write)
            if require_validation_read or write_completed:
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                tool_calls = ro_calls[:1]
                await self._emit_progress("phase.validation", {"iteration": f"{iter_idx+1}/{iters}"})
                messages.append({
                    "role": "system",
                    "content": "Validation step: run exactly one quick read-only check (e.g., fetch the item/list) to confirm the write succeeded. Do not perform any write operations. Then finalize."
                })
            elif not write_phase_allowed:
                ro_calls = [tc for tc in tool_calls if not self._is_write_tool_name(getattr(getattr(tc, 'function', None), 'name', ''))]
                if ro_calls:
                    tool_calls = ro_calls
                    write_phase_allowed = True
                    await self._emit_progress("phase.read_only", {"iteration": f"{iter_idx+1}/{iters}"})
                    messages.append({
                        "role": "system",
                        "content": "Phase 1 (read-only): gather information and identify exact targets. Do not perform writes yet. Next, you may perform the necessary write."
                    })
                else:
                    write_phase_allowed = True
                    await self._emit_progress("phase.write_enabled", {"iteration": f"{iter_idx+1}/{iters}"})
                    messages.append({
                        "role": "system",
                        "content": "Phase 2 (write): proceed to perform the necessary write operation now based on identified targets. Avoid additional discovery first unless strictly required."
                    })

            # Append assistant message that contains ONLY the tool calls we will actually execute
            messages.append({
                "role": "assistant",
                "content": "",
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
            
            # Process results asynchronously for better performance
            processed_messages = await self._process_results_async(flattened_results)
            messages.extend(processed_messages)
            # Post-write validation planning and finalize gating (mirrors sync path)
            write_success = self._contains_write_success(flattened_results)
            write_failure = self._contains_write_failure(flattened_results)
            if write_success:
                write_completed = True
                write_failed_once = False
                allow_finalize_on_failure = False
            elif write_failure:
                write_failed_once = True
                # Allow one quick diagnostic read-only step, then finalize gracefully
                allow_finalize_on_failure = True
                messages.append({
                    "role": "system",
                    "content": (
                        "The action didn't work as expected. Let me check what's available and then give you a helpful update with next steps. "
                        "I won't try the same action again, but I'll help you figure out what to do."
                    )
                })
            if write_success and not require_validation_read:
                require_validation_read = True
                await self._emit_progress("phase.validation_planned", {"iteration": f"{iter_idx+1}/{iters}"})
                messages.append({
                    "role": "system",
                    "content": "Write completed. Now perform a quick read-only validation (e.g., fetch the created/updated item) and then finalize. Do not perform any additional writes."
                })
            if require_validation_read and not write_success:
                # We were in validation mode this turn; validation done, finalize immediately
                require_validation_read = False
                messages.append({
                    "role": "system",
                    "content": "Validation complete. Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools."
                })
                try:
                    resp = await self._achat_once(messages, model, role, tool_choice_override="none")
                    try:
                        if getattr(self, "progress", None) is not None:
                            self.progress.stop_heartbeat("agent")
                    except Exception:
                        pass
                    await self._emit_progress("agent.finish", {"reason": "final_answer"})
                    return resp
                except Exception:
                    # If finalization call fails, fall back to next-turn finalize
                    force_finalize_next = True
                    next_tool_choice_override = "none"
            else:
                try:
                    allowed_to_finalize = self._results_indicate_finalizable(flattened_results)
                    if write_success:
                        allowed_to_finalize = False
                    if not allow_finalize_on_failure:
                        if seen_write_intent and not write_success:
                            allowed_to_finalize = False
                        if must_write and not write_success:
                            allowed_to_finalize = False
                    if allowed_to_finalize:
                        messages.append({
                            "role": "system",
                            "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools."
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
                                    tools=None,
                                    reasoning=sel.get("reasoningEffort"),
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
                            # Finalize immediately without streaming
                            try:
                                resp = await self._achat_once(messages, model, role, tool_choice_override="none")
                                try:
                                    if getattr(self, "progress", None) is not None:
                                        self.progress.stop_heartbeat("agent")
                                except Exception:
                                    pass
                                await self._emit_progress("agent.finish", {"reason": "final_answer"})
                                return resp
                            except Exception:
                                force_finalize_next = True
                except Exception:
                    force_finalize_next = False

            if force_finalize_next and (tool_calls is None or len(tool_calls) == 0):
                next_tool_choice_override = "none"

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
                        "content": "Here's what I found with the time available. I've done my best to help with your request!"
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
        _, sel = resolve_llm_selection(self.project_root, "chat")
        model = sel.get("model", "gpt-5-mini")
        return await self._arun_tools_loop(messages, model=model, role="chat", max_iters=None, stream_final_to_callback=stream_final_to_callback)

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

    async def _process_results_async(self, flattened_results: List[tuple]) -> List[Dict[str, Any]]:
        """Process tool results asynchronously for better performance.
        
        This method replaces the sequential result processing loop with concurrent
        processing of cache operations, summarization, and JSON serialization.
        """
        if not flattened_results:
            return []
        
        # Determine max items to keep in summaries and cache TTL
        list_max_default = int(self._tuning_cfg.get("list_max_default", 5))
        cache_ttl_sec = int(self._tuning_cfg.get("cache_ttl_short", 60))
        
        async def process_single_result(tool_call_id, name, result, attempts, cache_hit):
            """Process a single tool result asynchronously."""
            # Store raw result and attach ref_id for on-demand detail fetching
            ref_id = None
            try:
                ref_id = await asyncio.to_thread(put_tool_result, result, cache_ttl_sec)
            except Exception:
                ref_id = None

            # Summarize and minify tool output
            try:
                # If result set is very small (<=2), preserve raw fields (truncated) instead of lossy summary
                preserved = self._preserve_raw_if_small(result, max_keep=2)
                fam = self._classify_tool_family(name)
                fam_budgets = (self._tuning_cfg.get("tools_cfg", {}).get("listMaxItemsByFamily", {}) or {})
                list_max_items = int(fam_budgets.get(fam, list_max_default))
                summarized = preserved if preserved is not None else summarize_tool_result(name, result, max_items=list_max_items)
            except Exception:
                summarized = result

            # Create payload and serialize JSON asynchronously
            payload = {"ref_id": ref_id, "summary": summarized}
            content = await asyncio.to_thread(json.dumps, payload, separators=(",", ":"))
            
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": content,
            }
        
        # Process all results concurrently
        tasks = [process_single_result(*result) for result in flattened_results]
        processed_messages = await asyncio.gather(*tasks)
        
        return processed_messages

    async def aclose(self) -> None:
        """Close background tasks and shared network clients."""
        # Close progress broadcaster tasks
        try:
            if getattr(self, "progress", None) is not None:
                try:
                    await self.progress.aclose()  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            pass
        # Close shared aiohttp client (if any)
        try:
            from integrations.http_client import SharedHttpClient
            try:
                client = SharedHttpClient.instance()
                await client.close()
            except Exception:
                pass
        except Exception:
            pass


