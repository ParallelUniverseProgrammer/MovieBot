"""
Integration test for the smart recommendations tool to identify issues.

This test will help diagnose problems with the smart_recommendations tool
by testing various scenarios and checking for specific failure modes.
"""

import pytest
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, Mock

from bot.tools.registry import build_openai_tools_and_registry
from bot.sub_agent import SubAgent


@pytest.mark.integration
class TestSmartRecommendationsIntegration:
    """Integration tests for smart recommendations tool to identify issues."""

    @pytest.fixture(scope="class")
    def registry(self):
        """Create tool registry for testing."""
        project_root = Path(__file__).parent.parent
        # Mock the LLM client to avoid event loop issues during fixture creation
        from unittest.mock import Mock
        mock_llm = Mock()
        _, reg = build_openai_tools_and_registry(project_root, mock_llm)
        return reg

    @pytest.fixture(scope="class")
    def sub_agent(self):
        """Create SubAgent instance for direct testing."""
        project_root = Path(__file__).parent.parent
        api_key = os.getenv("OPENAI_API_KEY", "test-key")
        return SubAgent(api_key=api_key, project_root=project_root)

    @pytest.mark.asyncio
    async def test_smart_recommendations_tool_exists(self, registry):
        """Test that smart_recommendations tool is registered."""
        assert "smart_recommendations" in registry._tools
        tool_func = registry._tools["smart_recommendations"]
        assert callable(tool_func)
        assert asyncio.iscoroutinefunction(tool_func)

    @pytest.mark.asyncio
    async def test_smart_recommendations_basic_call(self, registry):
        """Test basic call to smart_recommendations tool."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            result = await registry.get("smart_recommendations")({
                "max_results": 2,
                "media_type": "movie"
            })
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "content" in result
                assert isinstance(result["content"], str)
                assert len(result["content"]) > 0
            else:
                # Log the error for debugging
                print(f"Smart recommendations failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            pytest.fail(f"Smart recommendations tool raised exception: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_seed_movie(self, registry):
        """Test smart_recommendations with a seed TMDb ID."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            # Use The Matrix (1999) as seed movie
            result = await registry.get("smart_recommendations")({
                "seed_tmdb_id": 603,
                "max_results": 3,
                "media_type": "movie"
            })
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "content" in result
                assert "seed_tmdb_id" in result
                assert result["seed_tmdb_id"] == 603
            else:
                print(f"Smart recommendations with seed failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            pytest.fail(f"Smart recommendations with seed raised exception: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_prompt(self, registry):
        """Test smart_recommendations with a user prompt."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            result = await registry.get("smart_recommendations")({
                "prompt": "I want action movies with good visual effects",
                "max_results": 2,
                "media_type": "movie"
            })
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "content" in result
            else:
                print(f"Smart recommendations with prompt failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            pytest.fail(f"Smart recommendations with prompt raised exception: {e}")

    @pytest.mark.asyncio
    async def test_sub_agent_direct_smart_recommendations(self, sub_agent):
        """Test SubAgent handle_smart_recommendations method directly."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            result = await sub_agent.handle_smart_recommendations(
                max_results=2,
                media_type="movie"
            )
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "content" in result
                assert "max_results" in result
                assert result["max_results"] == 2
            else:
                print(f"SubAgent smart recommendations failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            pytest.fail(f"SubAgent smart recommendations raised exception: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_timeout_behavior(self, registry):
        """Test smart_recommendations timeout behavior."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Test with a very short timeout to see how it handles timeouts
        try:
            result = await asyncio.wait_for(
                registry.get("smart_recommendations")({
                    "max_results": 1,
                    "media_type": "movie"
                }),
                timeout=5.0  # Very short timeout
            )
            
            assert isinstance(result, dict)
            # Should either succeed or fail gracefully, not raise timeout exception
            
        except asyncio.TimeoutError:
            pytest.fail("Smart recommendations tool timed out - this indicates a performance issue")

    @pytest.mark.asyncio
    async def test_smart_recommendations_dependencies(self, registry):
        """Test that smart_recommendations can access its dependencies."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Test that required tools are available
        required_tools = [
            "read_household_preferences",
            "tmdb_recommendations", 
            "tmdb_trending",
            "tmdb_popular_movies"
        ]
        
        for tool_name in required_tools:
            assert tool_name in registry._tools, f"Required tool {tool_name} not found in registry"

    @pytest.mark.asyncio
    async def test_smart_recommendations_error_scenarios(self, registry):
        """Test smart_recommendations with various error scenarios."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Test with invalid parameters
        test_cases = [
            {"max_results": -1},  # Invalid max_results
            {"media_type": "invalid_type"},  # Invalid media_type
            {"seed_tmdb_id": "not_a_number"},  # Invalid seed_tmdb_id
        ]
        
        for test_case in test_cases:
            try:
                result = await registry.get("smart_recommendations")(test_case)
                assert isinstance(result, dict)
                # Should handle invalid parameters gracefully
                if not result.get("success", True):
                    print(f"Smart recommendations handled invalid input gracefully: {test_case}")
                    
            except Exception as e:
                # Some exceptions might be expected for invalid inputs
                print(f"Smart recommendations raised exception for {test_case}: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_performance(self, registry):
        """Test smart_recommendations performance characteristics."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        import time
        
        start_time = time.time()
        try:
            result = await registry.get("smart_recommendations")({
                "max_results": 1,
                "media_type": "movie"
            })
            end_time = time.time()
            
            duration = end_time - start_time
            print(f"Smart recommendations took {duration:.2f} seconds")
            
            # Should complete within reasonable time (config timeout is 8000ms)
            assert duration < 15.0, f"Smart recommendations took too long: {duration:.2f}s"
            
            assert isinstance(result, dict)
            
        except Exception as e:
            pytest.fail(f"Smart recommendations performance test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_output_format(self, registry):
        """Test that smart_recommendations returns properly formatted output."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        try:
            result = await registry.get("smart_recommendations")({
                "max_results": 2,
                "media_type": "movie"
            })
            
            assert isinstance(result, dict)
            assert "success" in result
            assert "max_results" in result
            assert "media_type" in result
            
            if result["success"]:
                assert "content" in result
                content = result["content"]
                assert isinstance(content, str)
                assert len(content) > 0
                
                # Check that content looks like recommendations
                # Should contain movie titles and some reasoning
                print(f"Smart recommendations output: {content[:200]}...")
                
            else:
                # Log error details for debugging
                error = result.get("error", "Unknown error")
                print(f"Smart recommendations failed with error: {error}")
                
        except Exception as e:
            pytest.fail(f"Smart recommendations output format test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_household_preferences(self, registry):
        """Test that smart_recommendations can access household preferences."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # First test that household preferences can be loaded
        try:
            prefs_result = await registry.get("read_household_preferences")({"compact": True})
            assert isinstance(prefs_result, dict)
            print(f"Household preferences loaded: {bool(prefs_result.get('compact'))}")
            
            # Now test smart recommendations
            result = await registry.get("smart_recommendations")({
                "max_results": 1,
                "media_type": "movie"
            })
            
            assert isinstance(result, dict)
            
        except Exception as e:
            pytest.fail(f"Smart recommendations with preferences test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_debug_logging(self, registry):
        """Test smart_recommendations with debug logging to identify issues."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        import logging
        
        # Enable debug logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger("moviebot.sub_agent")
        logger.setLevel(logging.DEBUG)
        
        try:
            print("Starting smart recommendations with debug logging...")
            result = await registry.get("smart_recommendations")({
                "max_results": 1,
                "media_type": "movie"
            })
            
            print(f"Smart recommendations result: {result}")
            assert isinstance(result, dict)
            
        except Exception as e:
            print(f"Smart recommendations debug test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            pytest.fail(f"Smart recommendations debug test failed: {e}")
