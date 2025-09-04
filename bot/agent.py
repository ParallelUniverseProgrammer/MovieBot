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
        # Handle bundled tools
        if n in ["plex_library_overview", "system_health_overview", "tmdb_discovery_suite", "radarr_activity_overview", "sonarr_activity_overview"]:
            return "bundled"
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
        """Synchronous wrapper for the async _achat_once method."""
        self.log.debug("Using the deprecated synchronous _chat_once method, this should not happen.")
        import asyncio
        return asyncio.run(self._achat_once(messages, model, role, tool_choice_override))

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
            # No fallback - force async implementation
            sel = self._get_role_selection(role)
            params = dict(sel.get("params", {}))
            params["temperature"] = 1
            tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
            tools_to_send = None if tool_choice_value == "none" else self.openai_tools
            if tools_to_send is not None:
                params["tool_choice"] = tool_choice_value
            else:
                params.pop("tool_choice", None)
            # Force async implementation - no blocking fallbacks
            resp = await self.llm.achat(
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

    def _calculate_result_confidence(self, tool_name_and_results: List[tuple]) -> float:
        """Calculate confidence score (0.0-1.0) for finalization decision."""
        try:
            if not tool_name_and_results:
                return 0.0
            
            total_score = 0.0
            max_score = 0.0
            
            def _is_write_tool(name: str) -> bool:
                n = (name or "").lower()
                if any(x in n for x in ("add", "update", "delete", "monitor", "set_", "create", "remove")):
                    return True
                if n in ("update_household_preferences",):
                    return True
                return False

            def _calculate_tool_score(name: str, result: Any) -> float:
                """Calculate individual tool result score."""
                if not isinstance(result, dict):
                    return 0.5  # Unknown result type
                
                # Error penalty
                if result.get("ok") is False or "error" in result:
                    return 0.0
                
                # Write tool success bonus
                if _is_write_tool(str(name)):
                    return 1.0  # Write success is always high confidence
                
                # Read tool scoring based on content quality
                score = 0.8  # Much higher base score for successful read operations
                
                # Content richness bonus - more generous for simple queries
                for key in ("items", "results", "movies", "series", "episodes", "playlists", "collections"):
                    val = result.get(key)
                    if isinstance(val, list):
                        if len(val) > 0:
                            score += 0.5  # Increased bonus for having content (was 0.4)
                        if len(val) >= 1:  # Lowered threshold - even 1 item gets rich content bonus
                            score += 0.3  # Rich content bonus (was 0.2)
                        if len(val) >= 5:  # Lowered threshold for very rich content
                            score += 0.2  # Very rich content (was 0.1)
                
                # Metadata richness bonus - more generous scoring
                metadata_keys = ["title", "year", "rating", "genre", "summary", "description", "overview", "tagline"]
                metadata_count = sum(1 for key in metadata_keys if key in result and result[key])
                score += min(metadata_count * 0.08, 0.3)  # Increased per-field bonus and max bonus
                
                return min(score, 1.0)
            
            for _tc_id, name, result, _attempts, _cache_hit in tool_name_and_results:
                tool_score = _calculate_tool_score(name, result)
                tool_weight = 2.0 if _is_write_tool(str(name)) else 1.0  # Weight write tools more
                
                total_score += tool_score * tool_weight
                max_score += tool_weight
                
                # Debug logging for confidence calculation
                self.log.debug(f"Tool {name}: score={tool_score:.2f}, weight={tool_weight}, weighted_score={tool_score * tool_weight:.2f}")
            
            final_confidence = total_score / max_score if max_score > 0 else 0.0
            self.log.debug(f"Final confidence: {final_confidence:.2f} (total={total_score:.2f}, max={max_score:.2f})")
            return final_confidence
        except Exception:
            return 0.0

    def _results_indicate_finalizable(self, tool_name_and_results: List[tuple]) -> bool:
        """Enhanced heuristic to decide if we likely have enough info to finalize.

        Uses confidence scoring for more intelligent finalization decisions.
        """
        try:
            # Calculate confidence score
            confidence = self._calculate_result_confidence(tool_name_and_results)
            
            # High confidence threshold for finalization - lowered for better responsiveness
            if confidence >= 0.2:  # Much more lenient for read-only queries
                return True
            
            # Check for write success (always finalizable)
            any_write_success = False
            any_error = False
            
            def _is_write_tool(name: str) -> bool:
                n = (name or "").lower()
                if any(x in n for x in ("add", "update", "delete", "monitor", "set_", "create", "remove")):
                    return True
                if n in ("update_household_preferences",):
                    return True
                return False

            for _tc_id, name, result, _attempts, _cache_hit in tool_name_and_results:
                if isinstance(result, dict):
                    if result.get("ok") is False or "error" in result:
                        any_error = True
                    if _is_write_tool(str(name)) and ("error" not in result) and (result.get("ok") is not False):
                        any_write_success = True

            if any_write_success:
                return True
            if any_error:
                return False
            
            # Medium confidence with some content - lowered for better responsiveness
            return confidence >= 0.1  # Much more lenient for read-only queries
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

    def _group_tool_calls_for_batching(self, tool_calls: List[Any]) -> List[Any]:
        """Ultra-aggressive batching strategy with predictive execution and cross-family optimization.
        
        This method implements maximum performance batching based on:
        1. Tool family characteristics and API response times
        2. Operation type and safety requirements
        3. Optimal batch sizes per family (increased for better throughput)
        4. Cross-family batching opportunities
        5. Predictive tool grouping based on common patterns
        
        Returns a list where each element is either a single tool call or a list of tool calls
        that can be executed as a batch.
        """
        if not tool_calls:
            return []
        
        # Categorize tools by family and operation type
        ultra_fast_tools = []  # TMDb searches, Plex quick ops
        fast_tools = []        # TMDb details, Plex metadata
        medium_tools = []      # *arr reads, Plex complex ops
        slow_tools = []        # *arr writes, complex operations
        write_tools = []       # Any write operations
        
        for tc in tool_calls:
            name = tc.function.name
            family = self._classify_tool_family(name)
            
            # Enhanced categorization for better batching
            if family == "tmdb":
                if any(op in name for op in ["search", "discover", "trending", "popular"]):
                    ultra_fast_tools.append(tc)
                else:
                    fast_tools.append(tc)
            elif family == "plex":
                if any(op in name for op in ["search", "get_recently_added", "get_on_deck", "get_library_sections"]):
                    ultra_fast_tools.append(tc)
                elif any(op in name for op in ["get_", "recently_added", "on_deck"]):
                    fast_tools.append(tc)
                else:
                    medium_tools.append(tc)
            elif family in ["radarr", "sonarr"]:
                if "get_" in name or "system_status" in name or "quality_profiles" in name or "root_folders" in name:
                    fast_tools.append(tc)
                elif "add_" in name or "update_" in name or "delete_" in name or "monitor" in name:
                    slow_tools.append(tc)
                else:
                    medium_tools.append(tc)
            else:
                fast_tools.append(tc)
            
            # Track write operations separately
            if self._is_write_tool_name(name):
                write_tools.append(tc)
        
        # Create ultra-optimized batches with increased sizes
        result = []
        
        # Ultra-fast tools: batch up to 16 per batch (TMDb can handle high concurrency)
        if ultra_fast_tools:
            for i in range(0, len(ultra_fast_tools), 16):
                batch = ultra_fast_tools[i:i+16]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Fast tools: batch up to 12 per batch
        if fast_tools:
            for i in range(0, len(fast_tools), 12):
                batch = fast_tools[i:i+12]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Medium tools: batch up to 8 per batch (increased from 4)
        if medium_tools:
            for i in range(0, len(medium_tools), 8):
                batch = medium_tools[i:i+8]
                if len(batch) > 1:
                    result.append(batch)
                else:
                    result.append(batch[0])
        
        # Slow tools: batch up to 4 per batch (increased from 2)
        if slow_tools:
            for i in range(0, len(slow_tools), 4):
                batch = slow_tools[i:i+4]
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
        """Async version of _run_tools_loop with pipelined execution for maximum performance."""
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



        # Use LLM-based query classification for better decision making
        classification_result = await self._classify_query_complexity_llm(base_messages)
        complexity = classification_result["complexity"]
        confidence = classification_result["confidence"]
        reasoning = classification_result["reasoning"]
        requires_write = classification_result["requires_write"]
        suggested_tools = classification_result["suggested_tools"]
        estimated_iterations = classification_result["estimated_iterations"]
        
        # Use LLM-suggested iteration limit, but respect config maximums
        optimal_iters = min(estimated_iterations, iters)
        iters = optimal_iters
        
        # Add LLM classification guidance to system message
        if suggested_tools:
            classification_guidance = f"\n\nQUERY CLASSIFICATION: {complexity.upper()} (confidence: {confidence:.1f})\n"
            classification_guidance += f"Reasoning: {reasoning}\n"
            classification_guidance += f"Suggested tools: {', '.join(suggested_tools)}\n"
            classification_guidance += f"Estimated iterations: {estimated_iterations}\n"
            classification_guidance += "Use the suggested tools in parallel for optimal results."
            messages.append({"role": "system", "content": classification_guidance})
        
        must_write = requires_write or _user_intent_requires_write(base_messages)
        
        # Emit optimization details
        optimization_info = {
            "parallelism": parallelism_for_prompt, 
            "iters": iters,
            "complexity": complexity,
            "confidence": confidence,
            "reasoning": reasoning,
            "suggested_tools": suggested_tools,
            "must_write": must_write
        }
        await self._emit_progress("agent.start", optimization_info)
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
                # Use async file operations instead of asyncio.to_thread
                try:
                    import aiofiles
                    async with aiofiles.open(prefs_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        prefs = json.loads(content)
                except ImportError:
                    # Fallback to sync file operations if aiofiles not available
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
        
        # PIPELINED EXECUTION: Start first LLM call immediately
        current_llm_task = asyncio.create_task(self._achat_once(messages, model, role, tool_choice_override=next_tool_choice_override))
        llm_calls_count += 1
        next_tool_choice_override = None
        
        for iter_idx in range(iters):
            self.log.info(f"agent iteration {iter_idx+1}/{iters}")
            
            # Notify progress callback about LLM thinking
            await self._emit_progress("thinking", {"iteration": f"{iter_idx+1}/{iters}"})
            
            # Wait for current LLM call to complete
            last_response = await current_llm_task
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
                await self._emit_progress("agent.finish", {
                    "reason": "final_answer", 
                    "iterations_used": iter_idx + 1,
                    "optimization": "early_termination"
                })
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
                    # Batch execution - returns List[tuple]
                    return await self._execute_tool_batch(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                else:
                    # Single tool execution - returns tuple, wrap in list for consistency
                    result = await self._execute_single_tool(tc_or_group, timeout_ms, retry_max, backoff_base_ms, dedup_cache)
                    return [result]

            # Run with bounded concurrency
            sem = asyncio.Semaphore(parallelism)

            async def sem_wrapped(tc_or_group):
                async with sem:
                    return await run_one_or_batch(tc_or_group)

            # Execute tool calls first, then prepare for next iteration
            tool_execution_task = asyncio.gather(*[sem_wrapped(tc_or_group) for tc_or_group in tool_groups])
            
            # Wait for tool execution to complete first
            results = await tool_execution_task
            
            # Flatten results from batched executions
            flattened_results = []
            for result in results:
                if isinstance(result, list):
                    flattened_results.extend(result)
                else:
                    flattened_results.append(result)
            total_tool_calls += len(flattened_results)
            
            # Check for early termination tool call
            early_termination_requested = False
            termination_reason = ""
            termination_confidence = 0.0
            termination_summary = ""
            
            for _tc_id, name, result, _attempts, _cache_hit in flattened_results:
                if str(name) == "agent_early_terminate" and isinstance(result, dict) and result.get("termination_requested"):
                    early_termination_requested = True
                    termination_reason = result.get("reason", "Agent determined sufficient information gathered")
                    termination_confidence = result.get("confidence", 0.8)
                    termination_summary = result.get("summary", "")
                    self.log.info(f"Early termination requested: {termination_reason} (confidence: {termination_confidence:.2f})")
                    break
            
            # Process results asynchronously for better performance
            processed_messages = await self._process_results_async(flattened_results)
            messages.extend(processed_messages)
            
            # Handle early termination if requested
            if early_termination_requested:
                try:
                    # Use quick model for finalization
                    from config.loader import resolve_llm_selection
                    quick_provider, quick_sel = resolve_llm_selection(self.project_root, "quick")
                    quick_model = quick_sel.get("model")
                    
                    # Get the provider for the current model
                    current_provider, _ = resolve_llm_selection(self.project_root, role)
                    
                    # Add termination context to messages
                    messages.append({
                        "role": "system",
                        "content": f"Early termination requested: {termination_reason}\nConfidence: {termination_confidence:.2f}\nSummary: {termination_summary}\n\nFinalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools."
                    })
                    
                    if quick_model and quick_provider == current_provider:
                        self.log.info(f"Using quick model {quick_model} for early termination finalization")
                        resp = await self._achat_once(messages, quick_model, "quick", tool_choice_override="none")
                    else:
                        resp = await self._achat_once(messages, model, role, tool_choice_override="none")
                    
                    try:
                        if getattr(self, "progress", None) is not None:
                            self.progress.stop_heartbeat("agent")
                    except Exception:
                        pass
                    await self._emit_progress("agent.finish", {"reason": "early_termination", "termination_reason": termination_reason})
                    return resp
                except Exception as e:
                    self.log.warning(f"Early termination finalization failed: {e}, continuing with normal flow")
                    # Continue with normal flow if early termination fails
            
            # Start next LLM call after tool execution and result processing is complete
            next_llm_task = None
            if iter_idx < iters - 1:  # Not the last iteration
                next_llm_task = asyncio.create_task(
                    self._achat_once(messages, model, role, tool_choice_override=next_tool_choice_override)
                )
                llm_calls_count += 1
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
                    # Use quick model for finalization after validation
                    try:
                        from config.loader import resolve_llm_selection
                        quick_provider, quick_sel = resolve_llm_selection(self.project_root, "quick")
                        quick_model = quick_sel.get("model")
                        
                        # Get the provider for the current model
                        current_provider, _ = resolve_llm_selection(self.project_root, role)
                        
                        if quick_model and quick_provider == current_provider:
                            self.log.info(f"Using quick model {quick_model} for post-validation finalization")
                            resp = await self._achat_once(messages, quick_model, "quick", tool_choice_override="none")
                        else:
                            resp = await self._achat_once(messages, model, role, tool_choice_override="none")
                    except Exception as e:
                        self.log.warning(f"Failed to use quick model for post-validation finalization: {e}, falling back to {model}")
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
                # Let the agent decide when to terminate using the early termination tool
                # No automatic confidence-based termination - agent has full control
                pass

            # Update current_llm_task for next iteration
            if next_llm_task is not None:
                current_llm_task = next_llm_task
            else:
                # Last iteration - no more LLM calls
                current_llm_task = None

            if force_finalize_next and (tool_calls is None or len(tool_calls) == 0):
                next_tool_choice_override = "none"

        # Wait for any remaining LLM task to complete
        if current_llm_task is not None:
            await current_llm_task

        # Metrics
        try:
            elapsed_ms = int((_t.monotonic() - t_loop_start) * 1000)
            await self._emit_progress("agent.metrics", {"iters": iters, "llm_calls": llm_calls_count, "tool_calls": total_tool_calls, "elapsed_ms": elapsed_ms})
        except Exception:
            pass
        
        # Enhanced iteration limit handling with transparency
        final_response = await self._generate_iteration_limit_response(
            messages, model, role, iters, llm_calls_count, total_tool_calls, 
            elapsed_ms, write_completed, seen_write_intent, must_write
        )
        
        try:
            if getattr(self, "progress", None) is not None:
                self.progress.stop_heartbeat("agent")
        except Exception:
            pass
        await self._emit_progress("agent.finish", {"reason": "max_iters"})
        return final_response

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

    def _analyze_tool_execution_summary(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze tool execution history to provide a summary of what was accomplished."""
        try:
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            tool_calls = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
            
            # Count successful vs failed tools
            successful_tools = 0
            failed_tools = 0
            tool_families_used = set()
            write_operations = 0
            read_operations = 0
            
            for tool_msg in tool_messages:
                name = tool_msg.get("name", "")
                content = tool_msg.get("content", "")
                
                # Parse tool result
                try:
                    if content:
                        result_data = json.loads(content)
                        summary = result_data.get("summary", {})
                        
                        # Check if tool succeeded
                        if isinstance(summary, dict):
                            if summary.get("ok") is False or "error" in summary:
                                failed_tools += 1
                            else:
                                successful_tools += 1
                        else:
                            successful_tools += 1
                    else:
                        failed_tools += 1
                except Exception:
                    failed_tools += 1
                
                # Categorize by family and operation type
                family = self._classify_tool_family(name)
                tool_families_used.add(family)
                
                if self._is_write_tool_name(name):
                    write_operations += 1
                else:
                    read_operations += 1
            
            return {
                "total_tools": len(tool_messages),
                "successful_tools": successful_tools,
                "failed_tools": failed_tools,
                "tool_families": list(tool_families_used),
                "write_operations": write_operations,
                "read_operations": read_operations,
                "success_rate": successful_tools / len(tool_messages) if tool_messages else 0
            }
        except Exception:
            return {
                "total_tools": 0,
                "successful_tools": 0,
                "failed_tools": 0,
                "tool_families": [],
                "write_operations": 0,
                "read_operations": 0,
                "success_rate": 0
            }

    def _extract_key_findings(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract key findings from tool results to highlight in the final response."""
        try:
            findings = []
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            
            for tool_msg in tool_messages:
                name = tool_msg.get("name", "")
                content = tool_msg.get("content", "")
                
                try:
                    if content:
                        result_data = json.loads(content)
                        summary = result_data.get("summary", {})
                        
                        # Extract meaningful findings based on tool type
                        if isinstance(summary, dict):
                            if "movies" in summary and isinstance(summary["movies"], list) and summary["movies"]:
                                findings.append(f"Found {len(summary['movies'])} movies")
                            elif "series" in summary and isinstance(summary["series"], list) and summary["series"]:
                                findings.append(f"Found {len(summary['series'])} TV series")
                            elif "items" in summary and isinstance(summary["items"], list) and summary["items"]:
                                findings.append(f"Found {len(summary['items'])} items")
                            elif "ok" in summary and summary["ok"] is True:
                                if "add" in name or "monitor" in name:
                                    findings.append("Successfully added to your collection")
                                elif "update" in name:
                                    findings.append("Successfully updated")
                            elif "error" in summary:
                                findings.append(f"Encountered issue with {name}")
                except Exception:
                    continue
            
            return findings[:5]  # Limit to top 5 findings
        except Exception:
            return []

    def _get_pending_tool_calls(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract tool calls that were requested but may not have been executed due to iteration limits."""
        try:
            pending_tools = []
            assistant_messages = [m for m in messages if m.get("role") == "assistant" and m.get("tool_calls")]
            
            # Get the last assistant message with tool calls (most recent request)
            if assistant_messages:
                last_assistant = assistant_messages[-1]
                tool_calls = last_assistant.get("tool_calls", [])
                for tc in tool_calls:
                    if isinstance(tc, dict) and "function" in tc:
                        pending_tools.append(tc["function"].get("name", "unknown"))
                    elif hasattr(tc, 'function'):
                        pending_tools.append(tc.function.name)
            
            return pending_tools
        except Exception:
            return []

    async def _generate_iteration_limit_response(
        self, 
        messages: List[Dict[str, Any]], 
        model: str, 
        role: str, 
        iters: int, 
        llm_calls_count: int, 
        total_tool_calls: int, 
        elapsed_ms: int,
        write_completed: bool,
        seen_write_intent: bool,
        must_write: bool
    ) -> Dict[str, Any]:
        """Generate a comprehensive, personality-aware response when hitting iteration limits."""
        try:
            # Analyze what was accomplished
            tool_summary = self._analyze_tool_execution_summary(messages)
            key_findings = self._extract_key_findings(messages)
            pending_tools = self._get_pending_tool_calls(messages)
            
            # Determine the situation and appropriate tone
            if write_completed:
                situation = "completed_with_validation_needed"
                tone = "accomplished_but_incomplete"
            elif seen_write_intent and not write_completed:
                situation = "write_attempted_but_failed"
                tone = "helpful_but_limited"
            elif tool_summary["successful_tools"] > 0:
                situation = "partial_success"
                tone = "helpful_but_limited"
            else:
                situation = "minimal_progress"
                tone = "apologetic_but_helpful"
            
            # Build context for the LLM to generate a personalized response
            context_prompt = self._build_iteration_limit_context(
                situation, tone, iters, llm_calls_count, total_tool_calls, 
                elapsed_ms, tool_summary, key_findings, must_write, pending_tools
            )
            
            # Create a focused prompt for the final response using the full conversation context
            final_messages = messages + [
                {
                    "role": "system",
                    "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Be warm, friendly, and decisive. Use plain, upbeat language. Do not call tools. Use the information gathered from tools to answer the user's question directly."
                }
            ]
            
            # Generate the final response using the quick model
            try:
                # Try to use quick model for finalization
                try:
                    from config.loader import resolve_llm_selection
                    quick_provider, quick_sel = resolve_llm_selection(self.project_root, "quick")
                    quick_model = quick_sel.get("model")
                    
                    # Determine the provider for the original model
                    original_provider, _ = resolve_llm_selection(self.project_root, role)
                    
                    if quick_model and quick_provider == original_provider:
                        self.log.info(f"Using quick model {quick_model} for iteration limit finalization")
                        response = await self._achat_once(final_messages, quick_model, "quick", tool_choice_override="none")
                    else:
                        response = await self._achat_once(final_messages, model, role, tool_choice_override="none")
                except Exception as e:
                    self.log.warning(f"Failed to use quick model for iteration limit finalization: {e}, falling back to {model}")
                    response = await self._achat_once(final_messages, model, role, tool_choice_override="none")
                
                return response
            except Exception:
                # Fallback to a structured response if LLM generation fails
                return self._generate_fallback_iteration_response(
                    situation, tone, tool_summary, key_findings, elapsed_ms, pending_tools
                )
                
        except Exception:
            # Ultimate fallback
            return {
                "choices": [
                    {
                        "message": {
                            "content": "I hit my iteration limit while working on your request. I've done my best to help, but I may not have completed everything you needed. Feel free to ask me to try again or be more specific about what you're looking for!"
                        }
                    }
                ]
            }

    def _build_iteration_limit_context(
        self, 
        situation: str, 
        tone: str, 
        iters: int, 
        llm_calls_count: int, 
        total_tool_calls: int, 
        elapsed_ms: int,
        tool_summary: Dict[str, Any],
        key_findings: List[str],
        must_write: bool,
        pending_tools: List[str] = None
    ) -> str:
        """Build context for the LLM to generate an appropriate iteration limit response."""
        
        # Base context about the situation
        base_context = f"""You are MovieBot. I've reached my iteration limit ({iters} iterations) while working on a user request.

EXECUTION SUMMARY:
- Total time: {elapsed_ms/1000:.1f} seconds
- LLM calls made: {llm_calls_count}
- Tools executed: {total_tool_calls}
- Success rate: {tool_summary['success_rate']:.1%}
- Tool families used: {', '.join(tool_summary['tool_families']) or 'none'}

KEY FINDINGS: {', '.join(key_findings) if key_findings else 'Limited progress made'}"""

        # Add pending tools information if available
        if pending_tools:
            base_context += f"\n\nPENDING TOOLS: {', '.join(pending_tools)} (these were requested but couldn't be executed due to iteration limit)"

        base_context += f"""

SITUATION: {situation.upper().replace('_', ' ')}
TONE: {tone.upper().replace('_', ' ')}"""

        # Add situation-specific guidance
        if situation == "completed_with_validation_needed":
            base_context += """

You successfully completed the main task but may need validation. Be positive about what was accomplished while being honest about potential limitations."""
        
        elif situation == "write_attempted_but_failed":
            base_context += """

You attempted write operations but they may not have succeeded. Be helpful about what was tried and suggest next steps."""
        
        elif situation == "partial_success":
            base_context += """

You made good progress gathering information but may not have completed the full request. Highlight what you found and suggest how to proceed."""
        
        else:  # minimal_progress
            base_context += """

You made limited progress. Be honest about the limitations while remaining helpful and suggesting alternative approaches."""

        # Add specific guidance based on whether writes were required
        if must_write:
            base_context += """

IMPORTANT: The user's request required write operations. If you couldn't complete the writes, be clear about this and suggest specific next steps."""

        # Add personality and format guidance
        base_context += """

RESPONSE REQUIREMENTS:
- Stay warm, friendly, and decisive (your core personality)
- Be transparent about what you accomplished and what you couldn't complete
- Use plain, upbeat language
- Keep under 700 characters
- Use '-' bullets for lists
- Suggest specific next steps when appropriate
- Don't expose internal reasoning or technical details
- Be honest about limitations while remaining helpful

Generate a response that acknowledges the iteration limit while being genuinely helpful about what was accomplished and what the user should do next."""

        return base_context

    def _generate_fallback_iteration_response(
        self, 
        situation: str, 
        tone: str, 
        tool_summary: Dict[str, Any], 
        key_findings: List[str], 
        elapsed_ms: int,
        pending_tools: List[str] = None
    ) -> Dict[str, Any]:
        """Generate a structured fallback response when LLM generation fails."""
        
        # Build response based on situation
        if situation == "completed_with_validation_needed":
            content = "I've completed your request! ✅ I may need to do a quick validation check, but the main work is done."
        elif situation == "write_attempted_but_failed":
            content = "I tried to complete your request but ran into some issues. Let me help you figure out the next steps."
        elif situation == "partial_success":
            content = "I found some great stuff for you! Here's what I discovered before hitting my limit."
        else:
            content = "I hit my iteration limit while working on your request. Let me help you with what I found."
        
        # Add key findings if available
        if key_findings:
            content += f"\n\nKey findings:\n" + "\n".join(f"- {finding}" for finding in key_findings[:3])
        
        # Add execution summary
        if tool_summary["total_tools"] > 0:
            content += f"\n\nI executed {tool_summary['total_tools']} tools in {elapsed_ms/1000:.1f}s with a {tool_summary['success_rate']:.0%} success rate."
        
        # Add pending tools information if available
        if pending_tools:
            content += f"\n\nI was about to run: {', '.join(pending_tools)} but hit my limit."
        
        # Add next steps
        if situation in ["write_attempted_but_failed", "minimal_progress"]:
            content += "\n\nNext steps: Try asking me again with more specific details, or let me know if you'd like me to try a different approach!"
        
        return {
            "choices": [
                {
                    "message": {
                        "content": content
                    }
                }
            ]
        }


    async def aconverse(self, messages: List[Dict[str, str]], stream_final_to_callback: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
        """Async version of converse for non-blocking operations."""
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "chat")
        model = sel.get("model", "gpt-5-mini")
        return await self._arun_tools_loop(messages, model=model, role="chat", max_iters=None, stream_final_to_callback=stream_final_to_callback)

    async def arecommend(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Async version of recommend for non-blocking operations."""
        # Choose model from config
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "smart")
        model = sel.get("model", "gpt-5")
        return await self._arun_tools_loop(messages, model=model, role="smart")

    async def _classify_query_complexity_llm(self, msgs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Use LLM to classify query complexity and extract metadata for better decision making."""
        try:
            text_parts: List[str] = [str(m.get("content", "")) for m in msgs if m.get("role") == "user"]
            user_query = "\n".join(text_parts).strip()
            if not user_query:
                return {"complexity": "unknown", "confidence": 0.0, "reasoning": "Empty query"}
            
            # Use summarizer role for classification
            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, "summarizer")
            model = sel.get("model", "gpt-4.1-mini")
            
            classification_prompt = f"""Analyze this user query and classify its complexity for a movie/TV recommendation system.

User Query: "{user_query}"

Classify the query into one of these categories:
- simple: Basic information requests that can be answered with 1-2 tool calls (e.g., "what's new", "show me my movies", "system status")
- medium: Moderate complexity requiring 2-4 tool calls (e.g., "action movies from 2020", "similar to Inception", "rate this movie")
- complex: High complexity requiring 4+ tool calls (e.g., "add this movie to radarr", "find and download similar shows", "update my preferences")

Also determine:
- requires_write: Does this query need to modify data (add/update/delete)?
- suggested_tools: What tools would be most helpful (comma-separated)?
- estimated_iterations: How many iterations might be needed (1-6)?

Respond in JSON format:
{{
    "complexity": "simple|medium|complex",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "requires_write": true/false,
    "suggested_tools": ["tool1", "tool2"],
    "estimated_iterations": 1-6
}}"""

            messages = [{"role": "user", "content": classification_prompt}]
            
            # Use async chat for classification
            resp = await self._achat_once(messages, model, "summarizer")
            content = resp.choices[0].message.content
            
            # Handle case where LLM returns None content
            if content is None:
                self.log.warning("LLM returned None content for classification, using fallback")
                return {
                    "complexity": "medium",
                    "confidence": 0.5,
                    "reasoning": "LLM returned no content, using medium complexity fallback",
                    "requires_write": False,
                    "suggested_tools": [],
                    "estimated_iterations": 3
                }
            
            # Parse JSON response
            import json
            try:
                result = json.loads(content)
                return {
                    "complexity": result.get("complexity", "unknown"),
                    "confidence": float(result.get("confidence", 0.0)),
                    "reasoning": result.get("reasoning", ""),
                    "requires_write": bool(result.get("requires_write", False)),
                    "suggested_tools": result.get("suggested_tools", []),
                    "estimated_iterations": int(result.get("estimated_iterations", 3))
                }
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.log.error(f"Failed to parse LLM classification response: {e}")
                raise RuntimeError(f"LLM classification response parsing failed: {e}")
                
        except Exception as e:
            self.log.error(f"LLM classification failed: {e}")
            raise RuntimeError(f"LLM classification failed: {e}")




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
            """Process a single tool result asynchronously with no blocking operations."""
            # Store raw result and attach ref_id for on-demand detail fetching
            ref_id = None
            try:
                # Use async cache operations instead of asyncio.to_thread
                ref_id = await put_tool_result(result, cache_ttl_sec)
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

            # Create payload and serialize JSON directly (no blocking)
            payload = {"ref_id": ref_id, "summary": summarized}
            content = json.dumps(payload, separators=(",", ":"))
            
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


