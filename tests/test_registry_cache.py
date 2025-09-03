"""
Test the tool registry caching functionality.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

from bot.tools.registry_cache import RegistryCache, initialize_registry_cache, get_cached_registry


class TestRegistryCache:
    """Test the registry caching mechanism."""
    
    def test_singleton_behavior(self):
        """Test that RegistryCache is a singleton."""
        cache1 = RegistryCache()
        cache2 = RegistryCache()
        assert cache1 is cache2
    
    def test_initialization(self, tmp_path):
        """Test registry cache initialization."""
        cache = RegistryCache()
        
        # Should not be initialized initially
        assert not cache.is_initialized()
        
        # Initialize with a project root
        cache.initialize(tmp_path)
        
        # Should be initialized now
        assert cache.is_initialized()
        assert cache._project_root == tmp_path
        assert cache._base_registry is not None
        assert cache._base_openai_tools is not None
    
    def test_double_initialization(self, tmp_path):
        """Test that double initialization doesn't cause issues."""
        cache = RegistryCache()
        
        # Initialize twice
        cache.initialize(tmp_path)
        cache.initialize(tmp_path)  # Should be safe
        
        assert cache.is_initialized()
    
    def test_get_registry_without_llm(self, tmp_path):
        """Test getting registry without LLM client."""
        cache = RegistryCache()
        cache.initialize(tmp_path)
        
        openai_tools, registry = cache.get_registry()
        
        assert openai_tools is not None
        assert registry is not None
        assert len(registry._tools) > 0
    
    def test_get_registry_with_llm(self, tmp_path):
        """Test getting registry with LLM client."""
        cache = RegistryCache()
        cache.initialize(tmp_path)
        
        mock_llm = Mock()
        openai_tools, registry = cache.get_registry(mock_llm)
        
        assert openai_tools is not None
        assert registry is not None
        assert len(registry._tools) > 0
        
        # Should cache the LLM variant
        assert len(cache._llm_registry_cache) == 1
    
    def test_global_functions(self, tmp_path):
        """Test the global convenience functions."""
        # Test initialization
        initialize_registry_cache(tmp_path)
        
        # Test getting registry
        openai_tools, registry = get_cached_registry()
        assert openai_tools is not None
        assert registry is not None
    
    def test_cache_stats(self, tmp_path):
        """Test cache statistics."""
        cache = RegistryCache()
        
        # Before initialization
        stats = cache.get_stats()
        assert not stats["initialized"]
        assert stats["base_tools_count"] == 0
        assert stats["llm_variants_count"] == 0
        
        # After initialization
        cache.initialize(tmp_path)
        stats = cache.get_stats()
        assert stats["initialized"]
        assert stats["base_tools_count"] > 0
        assert stats["llm_variants_count"] == 0
        
        # After getting LLM variant
        mock_llm = Mock()
        cache.get_registry(mock_llm)
        stats = cache.get_stats()
        assert stats["llm_variants_count"] == 1
    
    def test_error_before_initialization(self):
        """Test that getting registry before initialization raises error."""
        cache = RegistryCache()
        
        with pytest.raises(RuntimeError, match="Registry cache not initialized"):
            cache.get_registry()
