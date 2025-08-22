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
        system_prompt = f"""You are a focused TV episode search agent. Your task is to search for individual episodes when season packs fail.

Series: {series_title} (ID: {series_id})
Season: {season_number}
Target Episodes: {', '.join(map(str, target_episodes))}

Your mission:
1. Search for each target episode individually using sonarr_search_episode
2. Monitor only the episodes that were successfully found
3. Provide a clear summary of what was found and what wasn't
4. Be efficient - use minimal context and focus only on this task

Available tools: sonarr_search_episode, sonarr_monitor_episodes, sonarr_get_episodes
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Search for episodes {', '.join(map(str, target_episodes))} from {series_title} Season {season_number} and monitor the ones you find."}
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
                return {
                    "success": True,
                    "content": final_response.choices[0].message.content,
                    "episodes_searched": target_episodes,
                    "series_id": series_id,
                    "season_number": season_number
                }
            else:
                return {
                    "success": True,
                    "content": content,
                    "episodes_searched": target_episodes,
                    "series_id": series_id,
                    "season_number": season_number
                }
                
        except Exception as e:
            self.log.error(f"Error in episode fallback search: {e}")
            return {
                "success": False,
                "error": str(e),
                "episodes_searched": target_episodes,
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
                
                # Parse args
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    result = {"ok": False, "error": "invalid_json", "details": str(e)}
                    results.append(result)
                    continue

                # Execute tool
                tool_func = self.tool_registry.get(name)
                result = await tool_func(args)
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
