#!/usr/bin/env python3
"""
Comprehensive test script for the smart recommendations tool.

This script tests the smart recommendations functionality in various scenarios
and provides detailed output about the tool's behavior.
"""

import asyncio
import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file first
env_path = project_root / ".env"
load_dotenv(env_path)

# Set up environment variables for testing (only if not already set)
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-testing")
os.environ.setdefault("TMDB_API_KEY", "test-tmdb-key")
os.environ.setdefault("PLEX_TOKEN", "test-plex-token")
os.environ.setdefault("PLEX_BASE_URL", "http://localhost:32400")

from bot.tools.registry_cache import initialize_registry_cache, get_cached_registry
from bot.sub_agent import SubAgent
from bot.tools.tool_impl import make_smart_recommendations


class SmartRecommendationsTester:
    """Test harness for smart recommendations functionality."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.registry = None
        self.sub_agent = None
        
    async def setup(self):
        """Initialize the test environment."""
        print("🔧 Setting up test environment...")
        
        try:
            # Initialize registry cache
            print("  - Initializing registry cache...")
            initialize_registry_cache(self.project_root)
            
            # Get registry
            print("  - Getting tool registry...")
            from unittest.mock import Mock
            mock_llm = Mock()
            _, self.registry = get_cached_registry(mock_llm)
            
            # Create SubAgent
            print("  - Creating SubAgent...")
            api_key = os.getenv("OPENAI_API_KEY", "test-key")
            self.sub_agent = SubAgent(api_key=api_key, project_root=self.project_root)
            
            print("✅ Test environment setup complete!")
            return True
            
        except Exception as e:
            print(f"❌ Setup failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_tool_registration(self):
        """Test that smart_recommendations tool is properly registered."""
        print("\n🔍 Testing tool registration...")
        
        try:
            assert "smart_recommendations" in self.registry._tools
            tool_func = self.registry._tools["smart_recommendations"]
            assert callable(tool_func)
            assert asyncio.iscoroutinefunction(tool_func)
            
            print("✅ smart_recommendations tool is properly registered")
            return True
            
        except Exception as e:
            print(f"❌ Tool registration test failed: {e}")
            return False
    
    async def test_basic_functionality(self):
        """Test basic smart recommendations functionality."""
        print("\n🎬 Testing basic smart recommendations...")
        
        try:
            result = await self.registry.get("smart_recommendations")({
                "max_results": 2,
                "media_type": "movie"
            })
            
            print(f"  Result: {json.dumps(result, indent=2)}")
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "content" in result
                assert isinstance(result["content"], str)
                assert len(result["content"]) > 0
                print("✅ Basic functionality test passed")
                return True
            else:
                print(f"⚠️  Basic functionality test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Basic functionality test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_with_seed_movie(self):
        """Test smart recommendations with a seed movie."""
        print("\n🎯 Testing with seed movie (The Matrix)...")
        
        try:
            result = await self.registry.get("smart_recommendations")({
                "seed_tmdb_id": 603,  # The Matrix (1999)
                "max_results": 3,
                "media_type": "movie"
            })
            
            print(f"  Result: {json.dumps(result, indent=2)}")
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "seed_tmdb_id" in result
                assert result["seed_tmdb_id"] == 603
                print("✅ Seed movie test passed")
                return True
            else:
                print(f"⚠️  Seed movie test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Seed movie test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_with_prompt(self):
        """Test smart recommendations with a user prompt."""
        print("\n💬 Testing with user prompt...")
        
        try:
            result = await self.registry.get("smart_recommendations")({
                "prompt": "I want action movies with good visual effects",
                "max_results": 2,
                "media_type": "movie"
            })
            
            print(f"  Result: {json.dumps(result, indent=2)}")
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                print("✅ User prompt test passed")
                return True
            else:
                print(f"⚠️  User prompt test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ User prompt test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_sub_agent_direct(self):
        """Test SubAgent handle_smart_recommendations method directly."""
        print("\n🤖 Testing SubAgent direct call...")
        
        try:
            result = await self.sub_agent.handle_smart_recommendations(
                max_results=2,
                media_type="movie"
            )
            
            print(f"  Result: {json.dumps(result, indent=2)}")
            
            assert isinstance(result, dict)
            assert "success" in result
            
            if result["success"]:
                assert "max_results" in result
                assert result["max_results"] == 2
                print("✅ SubAgent direct test passed")
                return True
            else:
                print(f"⚠️  SubAgent direct test failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ SubAgent direct test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_performance(self):
        """Test performance characteristics."""
        print("\n⏱️  Testing performance...")
        
        try:
            start_time = time.time()
            result = await self.registry.get("smart_recommendations")({
                "max_results": 1,
                "media_type": "movie"
            })
            end_time = time.time()
            
            duration = end_time - start_time
            print(f"  Duration: {duration:.2f} seconds")
            
            # Should complete within reasonable time
            if duration < 15.0:
                print("✅ Performance test passed")
                return True
            else:
                print(f"⚠️  Performance test failed: took too long ({duration:.2f}s)")
                return False
                
        except Exception as e:
            print(f"❌ Performance test failed: {e}")
            return False
    
    async def test_error_handling(self):
        """Test error handling with invalid inputs."""
        print("\n🚨 Testing error handling...")
        
        test_cases = [
            {"max_results": -1, "name": "negative max_results"},
            {"media_type": "invalid_type", "name": "invalid media_type"},
            {"seed_tmdb_id": "not_a_number", "name": "invalid seed_tmdb_id"},
        ]
        
        passed = 0
        for test_case in test_cases:
            name = test_case.pop("name")
            try:
                result = await self.registry.get("smart_recommendations")(test_case)
                print(f"  {name}: {result.get('success', 'unknown')}")
                if isinstance(result, dict):
                    passed += 1
            except Exception as e:
                print(f"  {name}: Exception (expected): {e}")
                passed += 1
        
        if passed == len(test_cases):
            print("✅ Error handling test passed")
            return True
        else:
            print(f"⚠️  Error handling test failed: {passed}/{len(test_cases)} cases handled")
            return False
    
    async def test_dependencies(self):
        """Test that required tools are available."""
        print("\n🔗 Testing dependencies...")
        
        required_tools = [
            "read_household_preferences",
            "tmdb_recommendations", 
            "tmdb_trending",
            "tmdb_popular_movies"
        ]
        
        missing_tools = []
        for tool_name in required_tools:
            if tool_name not in self.registry._tools:
                missing_tools.append(tool_name)
        
        if not missing_tools:
            print("✅ All required tools are available")
            return True
        else:
            print(f"❌ Missing tools: {missing_tools}")
            return False
    
    async def run_all_tests(self):
        """Run all tests and report results."""
        print("🚀 Starting Smart Recommendations Test Suite")
        print("=" * 50)
        
        # Setup
        if not await self.setup():
            print("❌ Setup failed, aborting tests")
            return False
        
        # Run tests
        tests = [
            ("Tool Registration", self.test_tool_registration),
            ("Dependencies", self.test_dependencies),
            ("Basic Functionality", self.test_basic_functionality),
            ("With Seed Movie", self.test_with_seed_movie),
            ("With User Prompt", self.test_with_prompt),
            ("SubAgent Direct", self.test_sub_agent_direct),
            ("Performance", self.test_performance),
            ("Error Handling", self.test_error_handling),
        ]
        
        results = {}
        for test_name, test_func in tests:
            try:
                results[test_name] = await test_func()
            except Exception as e:
                print(f"❌ {test_name} test crashed: {e}")
                results[test_name] = False
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")
        
        return passed == total


async def main():
    """Main test runner."""
    project_root = Path(__file__).parent
    
    # Check for required environment variables
    required_vars = ["OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please set these variables before running the tests.")
        return False
    
    tester = SmartRecommendationsTester(project_root)
    return await tester.run_all_tests()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
