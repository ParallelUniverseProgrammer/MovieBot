from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
import asyncio
import logging

from llm.clients import LLMClient
from .tools.registry import build_openai_tools_and_registry
from config.loader import load_runtime_config


class SubAgent:
    """
    Lightweight sub-agent for handling specific tasks like episode-level searches
    when season packs fail. Designed to be context-efficient and focused.
    """
    
    def __init__(self, *, api_key: str, project_root: Path, provider: str = "openai"):
        self.llm = LLMClient(api_key, provider=provider)
        self.openai_tools, self.tool_registry = build_openai_tools_and_registry(project_root, self.llm)
        self.project_root = project_root
        self.log = logging.getLogger("moviebot.sub_agent")
        
        # Use the same provider selection logic as the main agent
        from config.loader import load_settings
        settings = load_settings(project_root)
        
        # Choose provider: OpenRouter if available, otherwise OpenAI (same logic as main agent)
        if settings.openai_api_key:
            self.api_key = settings.openai_api_key
            self.provider = "openai"
        else:
            self.api_key = settings.openrouter_api_key or ""
            self.provider = "openrouter"
        
        # Recreate LLM client with correct provider
        self.llm = LLMClient(self.api_key, provider=self.provider)
        self.openai_tools, self.tool_registry = build_openai_tools_and_registry(project_root, self.llm)

    def _chat_once(self, messages: List[Dict[str, Any]], model: str) -> Any:
        """Single chat interaction with the LLM."""
        self.log.debug("SubAgent LLM.chat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        
        resp = self.llm.chat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            tool_choice="auto",
            temperature=0.7,  # Lower temperature for more focused responses
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

    async def _achat_once(self, messages: List[Dict[str, Any]], model: str) -> Any:
        """Async version of _chat_once for non-blocking LLM calls."""
        self.log.debug("SubAgent LLM.achat start", extra={
            "model": model,
            "message_count": len(messages),
        })
        
        resp = await self.llm.achat(
            model=model,
            messages=messages,
            tools=self.openai_tools,
            tool_choice="auto",
            temperature=0.7,  # Lower temperature for more focused responses
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
        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"
        else:
            model = "gpt-4o-mini"

        # Single iteration for focused task
        response = self._chat_once(messages, model)
        
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
                
                final_response = self._chat_once(final_messages, model)
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
        """Execute tool calls and return results."""
        results = []
        
        for tool_call in tool_calls:
            try:
                name = tool_call.function.name
                args_json = tool_call.function.arguments or "{}"
                
                self.log.info(f"Sub-agent executing tool: {name} with args: {args_json}")
                
                # Parse args
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    result = {"ok": False, "error": "invalid_json", "details": str(e)}
                    results.append(result)
                    self.log.error(f"JSON decode error in tool {name}: {e}")
                    continue

                # Execute tool
                tool_func = self.tool_registry.get(name)
                if not tool_func:
                    result = {"ok": False, "error": f"Tool {name} not found in registry"}
                    self.log.error(f"Tool {name} not found in registry")
                    results.append(result)
                    continue
                
                result = await tool_func(args)
                self.log.info(f"Tool {name} completed with result: {str(result)[:200]}...")
                results.append(result)
                
            except Exception as e:
                self.log.error(f"Error executing tool {name}: {e}")
                results.append({"ok": False, "error": str(e)})
        
        return results

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

        if hasattr(self.llm, 'provider') and self.llm.provider == "openrouter":
            model = "z-ai/glm-4.5-air:free"
        else:
            model = "gpt-4o-mini"

        response = self._chat_once(messages, model)
        
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
                
                final_response = self._chat_once(final_messages, model)
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
