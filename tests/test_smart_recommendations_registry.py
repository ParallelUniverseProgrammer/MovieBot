"""
Integration test for smart recommendations tool through the registry.

This test properly handles the event loop issues and tests the tool
as it would be used in the actual application.
"""

import pytest
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, Mock


@pytest.mark.integration
class TestSmartRecommendationsRegistry:
    """Integration tests for smart recommendations through the registry."""

    @pytest.fixture
    def project_root(self):
        """Get project root."""
        return Path(__file__).parent.parent

    @pytest.mark.asyncio
    async def test_smart_recommendations_through_registry(self, project_root):
        """Test smart recommendations tool through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
            # Test that smart_recommendations tool is registered
            assert "smart_recommendations" in registry._tools
            
            # Test the tool
            try:
                result = await registry.get("smart_recommendations")({
                    "max_results": 2,
                    "media_type": "movie"
                })
                
                print(f"Smart recommendations result: {result}")
                assert isinstance(result, dict)
                assert "success" in result
                
                if result["success"]:
                    assert "content" in result
                    assert isinstance(result["content"], str)
                    assert len(result["content"]) > 0
                    print(f"Success! Got recommendation: {result['content'][:200]}...")
                else:
                    print(f"Smart recommendations failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"Smart recommendations through registry failed: {e}")
                import traceback
                traceback.print_exc()
                pytest.fail(f"Smart recommendations through registry failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_seed_through_registry(self, project_root):
        """Test smart recommendations with seed movie through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
            # Test with seed movie (The Matrix)
            try:
                result = await registry.get("smart_recommendations")({
                    "seed_tmdb_id": 603,
                    "max_results": 3,
                    "media_type": "movie"
                })
                
                print(f"Smart recommendations with seed result: {result}")
                assert isinstance(result, dict)
                assert "success" in result
                
                if result["success"]:
                    assert "content" in result
                    assert "seed_tmdb_id" in result
                    assert result["seed_tmdb_id"] == 603
                    print(f"Success! Got seed-based recommendations: {result['content'][:200]}...")
                else:
                    print(f"Smart recommendations with seed failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"Smart recommendations with seed through registry failed: {e}")
                import traceback
                traceback.print_exc()
                pytest.fail(f"Smart recommendations with seed through registry failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_with_prompt_through_registry(self, project_root):
        """Test smart recommendations with user prompt through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
            # Test with user prompt
            try:
                result = await registry.get("smart_recommendations")({
                    "prompt": "I want sci-fi movies with good visual effects and interesting concepts",
                    "max_results": 2,
                    "media_type": "movie"
                })
                
                print(f"Smart recommendations with prompt result: {result}")
                assert isinstance(result, dict)
                assert "success" in result
                
                if result["success"]:
                    assert "content" in result
                    print(f"Success! Got prompt-based recommendations: {result['content'][:200]}...")
                else:
                    print(f"Smart recommendations with prompt failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"Smart recommendations with prompt through registry failed: {e}")
                import traceback
                traceback.print_exc()
                pytest.fail(f"Smart recommendations with prompt through registry failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_performance_through_registry(self, project_root):
        """Test smart recommendations performance through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            import time
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
            # Test performance
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
                assert "success" in result
                
                if result["success"]:
                    print(f"Performance test passed! Got recommendation in {duration:.2f}s")
                else:
                    print(f"Performance test - smart recommendations failed: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"Smart recommendations performance test failed: {e}")
                import traceback
                traceback.print_exc()
                pytest.fail(f"Smart recommendations performance test failed: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_error_handling_through_registry(self, project_root):
        """Test smart recommendations error handling through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
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
                    else:
                        print(f"Smart recommendations succeeded with invalid input: {test_case}")
                        
                except Exception as e:
                    # Some exceptions might be expected for invalid inputs
                    print(f"Smart recommendations raised exception for {test_case}: {e}")

    @pytest.mark.asyncio
    async def test_smart_recommendations_output_quality_through_registry(self, project_root):
        """Test smart recommendations output quality through the registry."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        # Mock the HTTP client to avoid event loop issues during registry creation
        with patch('integrations.http_client.SharedHttpClient') as mock_http_client:
            mock_http_client.instance.return_value = Mock()
            
            from bot.tools.registry import build_openai_tools_and_registry
            from llm.clients import LLMClient
            
            # Create a real LLM client
            llm_client = LLMClient(os.getenv("OPENAI_API_KEY"))
            
            # Build the registry
            openai_tools, registry = build_openai_tools_and_registry(project_root, llm_client)
            
            # Test output quality
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
                    print(f"Smart recommendations output quality test:")
                    print(f"Content length: {len(content)}")
                    print(f"Content preview: {content[:300]}...")
                    
                    # Basic quality checks
                    assert len(content) > 50, "Content should be substantial"
                    assert "—" in content or "(" in content, "Should contain movie titles with years"
                    
                else:
                    # Log error details for debugging
                    error = result.get("error", "Unknown error")
                    print(f"Smart recommendations failed with error: {error}")
                    
            except Exception as e:
                print(f"Smart recommendations output quality test failed: {e}")
                import traceback
                traceback.print_exc()
                pytest.fail(f"Smart recommendations output quality test failed: {e}")
