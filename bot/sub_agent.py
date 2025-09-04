from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
import asyncio
import logging

from llm.clients import LLMClient
from .tools.registry_cache import get_cached_registry
from config.loader import load_runtime_config


class SubAgent:
    """
    Lightweight sub-agent for handling specific tasks like episode-level searches
    when season packs fail. Designed to be context-efficient and focused.
    """
    
    def __init__(self, *, api_key: str, project_root: Path, provider: str = "openai"):
        # Resolve provider for worker role (lightweight tasks)
        from config.loader import resolve_llm_selection, load_settings
        prov, _sel = resolve_llm_selection(project_root, "worker", load_settings(project_root))
        self.llm = LLMClient(api_key, provider=prov)
        # Use cached tool registry (SubAgent doesn't need LLM client)
        self.openai_tools, self.tool_registry = get_cached_registry(None)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.sub_agent")

    def _chat_once(self, messages: List[Dict[str, Any]], model: str, role: str, tool_choice_override: str | None = None) -> Any:
        """Single chat interaction with the LLM."""
        self.log.debug("SubAgent LLM.chat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, role)
        params = dict(sel.get("params", {}))
        # gpt-5 family requires temperature exactly 1
        params["temperature"] = 1
        tool_choice_value = tool_choice_override if tool_choice_override is not None else params.pop("tool_choice", "auto")
        params["tool_choice"] = tool_choice_value
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            reasoning=sel.get("reasoningEffort"),
            **params,
        )

        try:
            content_preview = (resp.choices[0].message.content or "")[:100]
        except Exception:
            content_preview = "<no content>"
            
        self.log.debug("SubAgent LLM.chat done", extra={
            "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),
            "content_preview": content_preview,
        })
        return resp

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str, role: str, tool_choice_override: str | None = None) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        self.log.debug("SubAgent LLM.achat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        
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

        try:
            content_preview = (resp.choices[0].message.content or "")[:100]
        except Exception:
            content_preview = "<no content>"
            
        self.log.debug("SubAgent LLM.achat done", extra={
            "tool_calls": bool(getattr(getattr(resp.choices[0], 'message', {}), 'tool_calls', None)),
            "content_preview": content_preview,
        })
        return resp

    async def handle_episode_fallback_search(self, series_id: int, season_number: int, 
                                           series_title: str, target_episodes: List[int]) -> Dict[str, Any]:
        """
        Handle episode-level search when season pack fails.
        
        Args:
            series_id: Sonarr series ID
            season_number: Season number to search
            series_title: Series title for context
            target_episodes: List of episode numbers to search for
            
        Returns:
            Dict with search results and status
        """
        self.log.info(f"Starting episode fallback search for {series_title} S{season_number}, episodes: {target_episodes}")
        
        system_prompt = f"""You are a focused TV episode search agent. Your task is to search for individual episodes when season packs fail.

Series: {series_title} (ID: {series_id})
Season: {season_number}
Target Episodes: {', '.join(map(str, target_episodes))}

CRITICAL REQUIREMENTS:
1. You MUST search for ALL {len(target_episodes)} episodes listed above
2. Do NOT skip any episodes - search for each and every one
3. Use sonarr_get_episodes first to get episode IDs for the series
4. Then use sonarr_search_episode to search for each episode individually (more reliable than batch search)
5. Monitor only the episodes that were successfully found
6. Provide a detailed summary showing which episodes were found and which weren't
7. If you can't find all episodes, explain why and what you tried

WORKFLOW:
1. Call sonarr_get_episodes with series_id to get all episodes
2. Filter episodes by season_number to get the target season episodes
3. For each episode in the target episodes list, call sonarr_search_episode with the episode ID
4. After all searches complete, provide a summary of results

Available tools: sonarr_search_episodes, sonarr_search_episode, sonarr_monitor_episodes, sonarr_get_episodes

Remember: Search for ALL episodes, not just some of them!
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Follow this exact workflow to search for ALL {len(target_episodes)} episodes from {series_title} Season {season_number}:\n\n1. First get all episodes using sonarr_get_episodes with series_id {series_id}\n2. Then search for each episode individually using sonarr_search_episode with the episode ID\n3. Do NOT skip any episodes - search for each one\n4. Provide a detailed summary of what was found\n\nTarget episodes: {', '.join(map(str, target_episodes))}"}
        ]

        # Use a lightweight model for efficiency
        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "worker")
        model = sel.get("model", "gpt-5-nano")

        # Single iteration for focused task
        response = await self._achat_once(messages, model, "worker")
        
        try:
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            if tool_calls:
                self.log.info(f"Sub-agent executing {len(tool_calls)} tool calls for episode search")
                # Execute tool calls
                results = await self._execute_tool_calls(tool_calls)
                
                # Final response
                final_messages = messages + [
                    {"role": "assistant", "content": content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]}
                ] + [
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)}
                    for tc, result in zip(tool_calls, results)
                ]
                
                # Force finalization without further tool calls
                final_messages.append({"role": "system", "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."})
                final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                final_content = final_response.choices[0].message.content or ""
                
                self.log.info(f"Episode fallback search completed. Final response: {final_content[:200]}...")
                
                return {
                    "success": True,
                    "content": final_content,
                    "episodes_searched": target_episodes,
                    "episodes_requested": len(target_episodes),
                    "series_id": series_id,
                    "season_number": season_number,
                    "tool_calls_executed": len(tool_calls)
                }
            else:
                self.log.warning(f"No tool calls made by sub-agent for episode search")
                return {
                    "success": True,
                    "content": content,
                    "episodes_searched": target_episodes,
                    "episodes_requested": len(target_episodes),
                    "series_id": series_id,
                    "season_number": season_number,
                    "warning": "No tool calls made - episodes may not have been searched"
                }
                
        except Exception as e:
            self.log.error(f"Error in episode fallback search: {e}")
            return {
                "success": False,
                "error": str(e),
                "episodes_searched": target_episodes,
                "episodes_requested": len(target_episodes),
                "series_id": series_id,
                "season_number": season_number
            }

    async def _execute_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """Execute tool calls concurrently with bounded concurrency and timeouts.

        - Deduplicates identical calls in-batch
        - Respects tools.timeoutMs and tools.parallelism from runtime config
        """
        rc = load_runtime_config(self.project_root)
        timeout_ms = int((rc.get("tools", {}) or {}).get("timeoutMs", 8000))
        parallelism = int((rc.get("tools", {}) or {}).get("parallelism", 4))
        def _key_for(tc: Any) -> str:
            name = getattr(tc.function, "name", "<unknown>")
            args_json = getattr(tc.function, "arguments", "{}") or "{}"
            try:
                parsed = json.loads(args_json)
                norm = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
            except Exception:
                norm = str(args_json)
            return f"{name}:{norm}"

        async def _run_one(tc):
            name = getattr(tc.function, "name", "<unknown>")
            args_json = getattr(tc.function, "arguments", "{}") or "{}"
            try:
                self.log.info(f"Sub-agent executing tool: {name} with args: {args_json}")
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    self.log.error(f"JSON decode error in tool {name}: {e}")
                    return {"ok": False, "error": "invalid_json", "details": str(e)}

                tool_func = self.tool_registry.get(name)
                if not tool_func:
                    self.log.error(f"Tool {name} not found in registry")
                    return {"ok": False, "error": f"Tool {name} not found in registry"}

                try:
                    result = await asyncio.wait_for(tool_func(args), timeout=timeout_ms / 1000)
                except asyncio.TimeoutError:
                    return {"ok": False, "error": "timeout", "timeout_ms": timeout_ms, "name": name}
                self.log.info(f"Tool {name} completed with result: {str(result)[:200]}...")
                return result
            except Exception as e:
                self.log.error(f"Error executing tool {name}: {e}")
                return {"ok": False, "error": str(e)}

        # Deduplicate while preserving original order
        seen_keys = set()
        unique_tool_calls: List[Any] = []
        for tc in tool_calls:
            k = _key_for(tc)
            if k in seen_keys:
                continue
            seen_keys.add(k)
            unique_tool_calls.append(tc)

        if len(unique_tool_calls) != len(tool_calls):
            self.log.info(f"Sub-agent deduplicated {len(tool_calls) - len(unique_tool_calls)} duplicate tool call(s)")

        # Execute unique calls concurrently with bounded parallelism
        sem = asyncio.Semaphore(parallelism)
        async def _sem_wrapped(tc):
            async with sem:
                return await _run_one(tc)
        unique_results = await asyncio.gather(*[_sem_wrapped(tc) for tc in unique_tool_calls])

        # Map results back to the original tool_calls order
        key_to_result: Dict[str, Dict[str, Any]] = {}
        for tc, res in zip(unique_tool_calls, unique_results):
            key_to_result[_key_for(tc)] = res

        ordered_results: List[Dict[str, Any]] = [key_to_result[_key_for(tc)] for tc in tool_calls]
        return ordered_results

    async def handle_quality_fallback(self, series_id: int, target_quality: str, 
                                    fallback_qualities: List[str]) -> Dict[str, Any]:
        """
        Handle quality fallback when preferred quality isn't available.
        
        Args:
            series_id: Sonarr series ID
            target_quality: Preferred quality profile
            fallback_qualities: List of fallback quality profiles to try
            
        Returns:
            Dict with quality update results
        """
        system_prompt = f"""You are a quality profile management agent. Your task is to update a series quality profile when the preferred quality isn't available.

Series ID: {series_id}
Target Quality: {target_quality}
Fallback Qualities: {', '.join(fallback_qualities)}

Your mission:
1. Check available quality profiles
2. Update the series to use the best available fallback quality
3. Provide a clear summary of what was changed

Available tools: sonarr_quality_profiles, sonarr_update_series
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Update series {series_id} to use the best available quality from {', '.join(fallback_qualities)} since {target_quality} isn't available."}
        ]

        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "worker")
        model = sel.get("model", "gpt-5-nano")

        response = await self._achat_once(messages, model, "worker")
        
        try:
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            if tool_calls:
                results = await self._execute_tool_calls(tool_calls)
                
                final_messages = messages + [
                    {"role": "assistant", "content": content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]}
                ] + [
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)}
                    for tc, result in zip(tool_calls, results)
                ]
                
                final_messages.append({"role": "system", "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."})
                final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                return {
                    "success": True,
                    "content": final_response.choices[0].message.content,
                    "series_id": series_id,
                    "quality_updated": True
                }
            else:
                return {
                    "success": True,
                    "content": content,
                    "series_id": series_id,
                    "quality_updated": False
                }
                
        except Exception as e:
            self.log.error(f"Error in quality fallback: {e}")
            return {
                "success": False,
                "error": str(e),
                "series_id": series_id,
                "quality_updated": False
            }

    async def handle_smart_recommendations(
        self,
        *,
        seed_tmdb_id: int | None = None,
        prompt: str | None = None,
        max_results: int = 3,
        media_type: str = "movie",
    ) -> Dict[str, Any]:
        """
        Provide AI-powered recommendations using household preferences and TMDb signals.

        Single-iteration, context-efficient workflow:
        - Always load compact household preferences for grounding
        - If seed_tmdb_id provided (movie), fetch TMDb recommendations for it
        - Otherwise fetch trending/popular lists as candidates
        - Return a concise, friendly recommendation list with brief reasons

        Note: Availability checks are not performed here (kept lightweight).
        """
        self.log.info(
            f"Starting smart recommendations (seed_tmdb_id={seed_tmdb_id}, max_results={max_results}, media_type={media_type})"
        )
        
        try:
            system_prompt = (
            "You are a focused recommendation sub-agent. Use minimal tools in one pass.\n"
            "1) Load compact household preferences for taste grounding.\n"
            "2) If a seed TMDb id is provided and media_type==movie, call tmdb_recommendations for it.\n"
            "   Otherwise, fetch a reasonable small candidate set via tmdb_trending or tmdb_popular_movies (movies only).\n"
            "3) Select up to max_results items aligned with preferences.\n"
            "4) Produce a concise, user-facing list: Title (Year) — one-sentence why it fits.\n"
            "Do not call tools in the finalization step."
        )

            mt = (media_type or "movie").strip().lower()
            if mt not in ("movie", "tv", "all"):
                mt = "movie"

            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, "worker")
            model = sel.get("model", "gpt-5-nano")

            user_instructions = (
                f"Household-aligned recommendations. max_results={max_results}. media_type={mt}.\n"
                f"Seed TMDb id: {seed_tmdb_id if seed_tmdb_id is not None else '-'}\n"
                f"User prompt (optional): {prompt or '-'}\n"
                "Tools to consider: read_household_preferences (compact), tmdb_recommendations, tmdb_trending, tmdb_popular_movies, tmdb_movie_details."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_instructions},
            ]

            response = await self._achat_once(messages, model, "worker")

            try:
                content = response.choices[0].message.content or ""
                tool_calls = getattr(response.choices[0].message, "tool_calls", None)

                if tool_calls:
                    self.log.info(f"Sub-agent executing {len(tool_calls)} tool calls for smart recommendations")
                    results = await self._execute_tool_calls(tool_calls)

                    final_messages = messages + [
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                                }
                                for tc in tool_calls
                            ],
                        }
                    ] + [
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": json.dumps(result),
                        }
                        for tc, result in zip(tool_calls, results)
                    ]

                    final_messages.append({
                        "role": "system",
                        "content": "Finalize now: produce a concise, friendly list of up to max_results recommendations with one-sentence reasons. Do not call tools.",
                    })
                    final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                    final_content = final_response.choices[0].message.content or ""
                    self.log.info(f"Smart recommendations completed. Final response: {final_content[:200]}...")
                    return {
                        "success": True,
                        "content": final_content,
                        "seed_tmdb_id": seed_tmdb_id,
                        "max_results": max_results,
                        "media_type": mt,
                    }
                else:
                    self.log.warning("No tool calls made by sub-agent for smart recommendations")
                    return {
                        "success": True,
                        "content": content,
                        "seed_tmdb_id": seed_tmdb_id,
                        "max_results": max_results,
                        "media_type": mt,
                        "warning": "No tool calls made",
                    }
            except Exception as e:
                self.log.error(f"Error in smart recommendations: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "seed_tmdb_id": seed_tmdb_id,
                    "max_results": max_results,
                    "media_type": mt,
                }
        except Exception as e:
            self.log.error(f"Error in smart recommendations (outer): {e}")
            return {
                "success": False,
                "error": str(e),
                "seed_tmdb_id": seed_tmdb_id,
                "max_results": max_results,
                "media_type": media_type,
            }

    async def handle_intelligent_search(
        self,
        *,
        query: str,
        limit: int = 10,
        response_level: str | None = None,
    ) -> Dict[str, Any]:
        """
        Perform intelligent search by combining TMDb multi-search with Plex search, then
        produce a concise, deduplicated summary with relevance notes.

        Single-iteration flow:
        - Call tmdb_search_multi(query)
        - Call search_plex(query, limit, response_level=compact)
        - Finalize with a merged view (no further tool calls)
        """
        q = (query or "").strip()
        if not q:
            return {"success": False, "error": "query_required"}

        self.log.info(f"Starting intelligent search for query='{q}', limit={limit}")
        
        try:
            system_prompt = (
            "You are a focused search sub-agent. In a single batch of tool calls:\n"
            "1) Call tmdb_search_multi with the raw user query.\n"
            "2) Call search_plex with the same query (limit as provided, response_level compact).\n"
            "Then finalize with a concise merged list highlighting strong matches and availability hints.\n"
            "Do not call tools in the finalization step."
        )

            from config.loader import resolve_llm_selection
            _, sel = resolve_llm_selection(self.project_root, "worker")
            model = sel.get("model", "gpt-5-nano")

            user_instructions = (
                f"query={q}\nlimit={int(limit)}\nresponse_level={response_level or 'compact'}"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_instructions},
            ]

            response = await self._achat_once(messages, model, "worker")

            try:
                content = response.choices[0].message.content or ""
                tool_calls = getattr(response.choices[0].message, "tool_calls", None)

                if tool_calls:
                    self.log.info(f"Sub-agent executing {len(tool_calls)} tool calls for intelligent search")
                    results = await self._execute_tool_calls(tool_calls)

                    final_messages = messages + [
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                                }
                                for tc in tool_calls
                            ],
                        }
                    ] + [
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": json.dumps(result),
                        }
                        for tc, result in zip(tool_calls, results)
                    ]

                    final_messages.append({
                        "role": "system",
                        "content": "Finalize now: produce a concise merged result list with brief explanations and availability hints. Do not call tools.",
                    })
                    final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                    final_content = final_response.choices[0].message.content or ""
                    self.log.info(f"Intelligent search completed. Final response: {final_content[:200]}...")
                    return {
                        "success": True,
                        "content": final_content,
                        "query": q,
                        "limit": int(limit),
                    }
                else:
                    self.log.warning("No tool calls made by sub-agent for intelligent search")
                    return {
                        "success": True,
                        "content": content,
                        "query": q,
                        "limit": int(limit),
                        "warning": "No tool calls made",
                    }
            except Exception as e:
                self.log.error(f"Error in intelligent search: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "query": q,
                    "limit": int(limit),
                }
        except Exception as e:
            self.log.error(f"Error in intelligent search (outer): {e}")
            return {
                "success": False,
                "error": str(e),
                "query": q,
                "limit": int(limit),
            }

    async def handle_radarr_movie_addition_fallback(
        self,
        *,
        tmdb_id: int,
        movie_title: str,
        preferred_quality: str | None = None,
        fallback_qualities: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Handle movie addition with quality fallback when preferred quality isn't available.
        
        Args:
            tmdb_id: TMDb movie ID
            movie_title: Movie title for context
            preferred_quality: Preferred quality profile name
            fallback_qualities: List of fallback quality profiles to try
            
        Returns:
            Dict with movie addition results and quality used
        """
        self.log.info(f"Starting Radarr movie addition fallback for {movie_title} (TMDb ID: {tmdb_id})")
        
        system_prompt = f"""You are a focused Radarr movie addition agent. Your task is to add a movie with intelligent quality fallback.

Movie: {movie_title} (TMDb ID: {tmdb_id})
Preferred Quality: {preferred_quality or 'default'}
Fallback Qualities: {', '.join(fallback_qualities) if fallback_qualities else 'none specified'}

CRITICAL REQUIREMENTS:
1. First check available quality profiles using radarr_quality_profiles
2. If preferred quality is specified, try to use it
3. If preferred quality isn't available, use the best available fallback quality
4. Add the movie using radarr_add_movie with the selected quality
5. If the movie already exists, acknowledge this gracefully - it's not an error
6. Provide a clear summary of what was added or what already exists

WORKFLOW:
1. Call radarr_quality_profiles to get available quality profiles
2. Select the best available quality (preferred > fallback > default)
3. Call radarr_add_movie with the selected quality profile ID
4. If the response indicates "already_exists": true, treat this as success
5. Provide a summary of the addition or existing status

Available tools: radarr_quality_profiles, radarr_add_movie, radarr_root_folders

Remember: 
- Always add the movie even if the preferred quality isn't available
- If a movie already exists, this is SUCCESS, not an error - acknowledge it gracefully
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Add movie '{movie_title}' (TMDb ID: {tmdb_id}) to Radarr with intelligent quality selection. Preferred: {preferred_quality or 'default'}, Fallbacks: {', '.join(fallback_qualities) if fallback_qualities else 'none'}."}
        ]

        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "worker")
        model = sel.get("model", "gpt-5-nano")

        response = await self._achat_once(messages, model, "worker")
        
        try:
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            if tool_calls:
                self.log.info(f"Sub-agent executing {len(tool_calls)} tool calls for Radarr movie addition")
                results = await self._execute_tool_calls(tool_calls)
                
                final_messages = messages + [
                    {"role": "assistant", "content": content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]}
                ] + [
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)}
                    for tc, result in zip(tool_calls, results)
                ]
                
                final_messages.append({"role": "system", "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."})
                final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                final_content = final_response.choices[0].message.content or ""
                
                self.log.info(f"Radarr movie addition completed. Final response: {final_content[:200]}...")
                
                return {
                    "success": True,
                    "content": final_content,
                    "tmdb_id": tmdb_id,
                    "movie_title": movie_title,
                    "preferred_quality": preferred_quality,
                    "fallback_qualities": fallback_qualities,
                    "tool_calls_executed": len(tool_calls)
                }
            else:
                self.log.warning(f"No tool calls made by sub-agent for Radarr movie addition")
                return {
                    "success": True,
                    "content": content,
                    "tmdb_id": tmdb_id,
                    "movie_title": movie_title,
                    "preferred_quality": preferred_quality,
                    "fallback_qualities": fallback_qualities,
                    "warning": "No tool calls made - movie may not have been added"
                }
                
        except Exception as e:
            self.log.error(f"Error in Radarr movie addition fallback: {e}")
            return {
                "success": False,
                "error": str(e),
                "tmdb_id": tmdb_id,
                "movie_title": movie_title,
                "preferred_quality": preferred_quality,
                "fallback_qualities": fallback_qualities
            }

    async def handle_radarr_activity_check(
        self,
        *,
        check_queue: bool = True,
        check_wanted: bool = True,
        check_calendar: bool = False,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Check Radarr activity status including queue, wanted movies, and upcoming releases.
        
        Args:
            check_queue: Whether to check the download queue
            check_wanted: Whether to check wanted/missing movies
            check_calendar: Whether to check upcoming releases
            max_results: Maximum number of results to return per category
            
        Returns:
            Dict with activity status and summaries
        """
        self.log.info(f"Starting Radarr activity check (queue={check_queue}, wanted={check_wanted}, calendar={check_calendar})")
        
        system_prompt = f"""You are a focused Radarr activity monitoring agent. Your task is to check current activity status.

Activity Checks:
- Queue Status: {check_queue}
- Wanted Movies: {check_wanted}  
- Upcoming Calendar: {check_calendar}
- Max Results: {max_results}

CRITICAL REQUIREMENTS:
1. This is a READ-ONLY operation - do not make any changes to Radarr
2. Check the specified activity categories
3. Provide concise summaries of current status
4. Highlight any issues or notable activity

WORKFLOW:
1. Check queue status if requested using radarr_get_queue
2. Check wanted movies if requested using radarr_get_wanted
3. Check calendar if requested using radarr_get_calendar
4. Provide a summary of current activity

Available tools: radarr_get_queue, radarr_get_wanted, radarr_get_calendar, radarr_system_status

Remember: This is information gathering only - no modifications!
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Check Radarr activity status. Queue: {check_queue}, Wanted: {check_wanted}, Calendar: {check_calendar}. Max {max_results} results per category."}
        ]

        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "worker")
        model = sel.get("model", "gpt-5-nano")

        response = await self._achat_once(messages, model, "worker")
        
        try:
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            if tool_calls:
                self.log.info(f"Sub-agent executing {len(tool_calls)} tool calls for Radarr activity check")
                results = await self._execute_tool_calls(tool_calls)
                
                final_messages = messages + [
                    {"role": "assistant", "content": content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]}
                ] + [
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)}
                    for tc, result in zip(tool_calls, results)
                ]
                
                final_messages.append({"role": "system", "content": "Finalize now: produce a concise, friendly user-facing summary of Radarr activity with no meta-instructions or headings. Do not call tools."})
                final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                final_content = final_response.choices[0].message.content or ""
                
                self.log.info(f"Radarr activity check completed. Final response: {final_content[:200]}...")
                
                return {
                    "success": True,
                    "content": final_content,
                    "check_queue": check_queue,
                    "check_wanted": check_wanted,
                    "check_calendar": check_calendar,
                    "max_results": max_results,
                    "tool_calls_executed": len(tool_calls)
                }
            else:
                self.log.warning(f"No tool calls made by sub-agent for Radarr activity check")
                return {
                    "success": True,
                    "content": content,
                    "check_queue": check_queue,
                    "check_wanted": check_wanted,
                    "check_calendar": check_calendar,
                    "max_results": max_results,
                    "warning": "No tool calls made - activity may not have been checked"
                }
                
        except Exception as e:
            self.log.error(f"Error in Radarr activity check: {e}")
            return {
                "success": False,
                "error": str(e),
                "check_queue": check_queue,
                "check_wanted": check_wanted,
                "check_calendar": check_calendar,
                "max_results": max_results
            }

    async def handle_radarr_quality_fallback(
        self,
        *,
        movie_id: int,
        movie_title: str,
        target_quality: str,
        fallback_qualities: List[str],
    ) -> Dict[str, Any]:
        """
        Handle quality fallback for existing movies when preferred quality isn't available.
        
        Args:
            movie_id: Radarr movie ID
            movie_title: Movie title for context
            target_quality: Preferred quality profile name
            fallback_qualities: List of fallback quality profiles to try
            
        Returns:
            Dict with quality update results
        """
        self.log.info(f"Starting Radarr quality fallback for {movie_title} (ID: {movie_id})")
        
        system_prompt = f"""You are a focused Radarr quality management agent. Your task is to update a movie's quality profile when the preferred quality isn't available.

Movie: {movie_title} (ID: {movie_id})
Target Quality: {target_quality}
Fallback Qualities: {', '.join(fallback_qualities)}

Your mission:
1. Check available quality profiles using radarr_quality_profiles
2. Update the movie to use the best available fallback quality
3. Provide a clear summary of what was changed

WORKFLOW:
1. Call radarr_quality_profiles to get available quality profiles
2. Select the best available fallback quality
3. Call radarr_update_movie with the new quality profile ID
4. Provide a summary of the quality change

Available tools: radarr_quality_profiles, radarr_update_movie, radarr_get_movies

Remember: Update to the best available quality from the fallback list!
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Update movie '{movie_title}' (ID: {movie_id}) to use the best available quality from {', '.join(fallback_qualities)} since {target_quality} isn't available."}
        ]

        from config.loader import resolve_llm_selection
        _, sel = resolve_llm_selection(self.project_root, "worker")
        model = sel.get("model", "gpt-5-nano")

        response = await self._achat_once(messages, model, "worker")
        
        try:
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            if tool_calls:
                results = await self._execute_tool_calls(tool_calls)
                
                final_messages = messages + [
                    {"role": "assistant", "content": content, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]}
                ] + [
                    {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": json.dumps(result)}
                    for tc, result in zip(tool_calls, results)
                ]
                
                final_messages.append({"role": "system", "content": "Finalize now: produce a concise, friendly user-facing reply with no meta-instructions or headings. Do not call tools."})
                final_response = await self._achat_once(final_messages, model, "worker", tool_choice_override="none")
                return {
                    "success": True,
                    "content": final_response.choices[0].message.content,
                    "movie_id": movie_id,
                    "movie_title": movie_title,
                    "target_quality": target_quality,
                    "fallback_qualities": fallback_qualities,
                    "quality_updated": True
                }
            else:
                return {
                    "success": True,
                    "content": content,
                    "movie_id": movie_id,
                    "movie_title": movie_title,
                    "target_quality": target_quality,
                    "fallback_qualities": fallback_qualities,
                    "quality_updated": False
                }
                
        except Exception as e:
            self.log.error(f"Error in Radarr quality fallback: {e}")
            return {
                "success": False,
                "error": str(e),
                "movie_id": movie_id,
                "movie_title": movie_title,
                "target_quality": target_quality,
                "fallback_qualities": fallback_qualities,
                "quality_updated": False
            }
