"""
Simple test for smart recommendations tool to identify issues without complex setup.
"""

import pytest
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock

from bot.sub_agent import SubAgent


@pytest.mark.integration
class TestSmartRecommendationsSimple:
    """Simple integration tests for smart recommendations tool."""

    @pytest.fixture
    def project_root(self):
        """Get project root."""
        return Path(__file__).parent.parent

    @pytest.mark.asyncio
    async def test_sub_agent_initialization(self, project_root):
        """Test that SubAgent can be initialized."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            assert sub_agent is not None
            assert sub_agent.llm is not None
            assert sub_agent.tool_registry is not None
        except Exception as e:
            pytest.fail(f"SubAgent initialization failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_direct_call(self, project_root):
        """Test smart recommendations with direct SubAgent call."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            
            result = await sub_agent.handle_smart_recommendations(
                max_results=1,
                media_type="movie"
            )
            
            print(f"Smart recommendations result: {result}")
            assert isinstance(result, dict)
            assert "success" in result
            
            if not result["success"]:
                print(f"Smart recommendations failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"Smart recommendations direct call failed: {e}")
            import traceback
            traceback.print_exc()
            pytest.fail(f"Smart recommendations direct call failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_seed(self, project_root):
        """Test smart recommendations with seed movie."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            
            # Use The Matrix (1999) as seed
            result = await sub_agent.handle_smart_recommendations(
                seed_tmdb_id=603,
                max_results=2,
                media_type="movie"
            )
            
            print(f"Smart recommendations with seed result: {result}")
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "seed_tmdb_id" in result
                assert result["seed_tmdb_id"] == 603
            else:
                print(f"Smart recommendations with seed failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"Smart recommendations with seed failed: {e}")
            import traceback
            traceback.print_exc()
            pytest.fail(f"Smart recommendations with seed failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_tool_registry_access(self, project_root):
        """Test that SubAgent can access required tools."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            
            # Check that required tools are available
            required_tools = [
                "read_household_preferences",
                "tmdb_recommendations",
                "tmdb_trending", 
                "tmdb_popular_movies"
            ]
            
            for tool_name in required_tools:
                assert tool_name in sub_agent.tool_registry._tools, f"Tool {tool_name} not found"
                
            print("All required tools are available in SubAgent registry")
            
        except Exception as e:
            pytest.fail(f"Tool registry access test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_llm_call(self, project_root):
        """Test that SubAgent can make LLM calls."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            
            # Test a simple LLM call
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello, world!'"}
            ]
            
            response = await sub_agent._achat_once(messages, "gpt-4o-mini", "worker")
            
            assert response is not None
            assert hasattr(response, 'choices')
            assert len(response.choices) > 0
            
            content = response.choices[0].message.content
            assert content is not None
            assert len(content) > 0
            
            print(f"LLM call successful: {content[:100]}...")
            
        except Exception as e:
            print(f"LLM call test failed: {e}")
            import traceback
            traceback.print_exc()
            pytest.fail(f"LLM call test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_step_by_step(self, project_root):
        """Test smart recommendations step by step to identify where it fails."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            sub_agent = SubAgent(
                api_key=os.getenv("OPENAI_API_KEY"),
                project_root=project_root
            )
            
            # Step 1: Test system prompt and user instructions
            system_prompt = (
                "You are a focused recommendation sub-agent. Use minimal tools in one pass.\n"
                "1) Load compact household preferences for taste grounding.\n"
                "2) If a seed TMDb id is provided and media_type==movie, call tmdb_recommendations for it.\n"
                "   Otherwise, fetch a reasonable small candidate set via tmdb_trending or tmdb_popular_movies (movies only).\n"
                "3) Select up to max_results items aligned with preferences.\n"
                "4) Produce a concise, user-facing list: Title (Year) — one-sentence why it fits.\n"
                "Do not call tools in the finalization step."
            )
            
            user_instructions = (
                "Household-aligned recommendations. max_results=1. media_type=movie.\n"
                "Seed TMDb id: -\n"
                "User prompt (optional): -\n"
                "Tools to consider: read_household_preferences (compact), tmdb_recommendations, tmdb_trending, tmdb_popular_movies, tmdb_movie_details."
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_instructions},
            ]
            
            print("Step 1: Making initial LLM call...")
            response = await sub_agent._achat_once(messages, "gpt-4o-mini", "worker")
            
            assert response is not None
            content = response.choices[0].message.content or ""
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            
            print(f"Step 1 result - Content: {content[:200]}...")
            print(f"Step 1 result - Tool calls: {len(tool_calls) if tool_calls else 0}")
            
            if tool_calls:
                print("Step 2: Executing tool calls...")
                results = await sub_agent._execute_tool_calls(tool_calls)
                print(f"Step 2 result - Tool results: {len(results)}")
                
                # Step 3: Finalization
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
                        "content": str(result),  # Convert to string for JSON serialization
                    }
                    for tc, result in zip(tool_calls, results)
                ]
                
                final_messages.append({
                    "role": "system",
                    "content": "Finalize now: produce a concise, friendly list of up to max_results recommendations with one-sentence reasons. Do not call tools.",
                })
                
                print("Step 3: Making finalization call...")
                final_response = await sub_agent._achat_once(final_messages, "gpt-4o-mini", "worker", tool_choice_override="none")
                final_content = final_response.choices[0].message.content or ""
                
                print(f"Step 3 result - Final content: {final_content}")
                
                result = {
                    "success": True,
                    "content": final_content,
                    "max_results": 1,
                    "media_type": "movie",
                }
            else:
                print("No tool calls made - using direct content")
                result = {
                    "success": True,
                    "content": content,
                    "max_results": 1,
                    "media_type": "movie",
                    "warning": "No tool calls made",
                }
            
            print(f"Final result: {result}")
            assert isinstance(result, dict)
            assert "success" in result
            
        except Exception as e:
            print(f"Step-by-step test failed: {e}")
            import traceback
            traceback.print_exc()
            pytest.fail(f"Step-by-step test failed: {e}")
