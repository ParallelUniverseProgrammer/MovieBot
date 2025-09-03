"""
Global tool registry cache to avoid rebuilding the registry on every Agent/SubAgent instantiation.

This module provides a singleton cache that builds the tool registry once at startup
and reuses it across all agent instances, significantly improving performance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import logging
import threading

from .registry import build_openai_tools_and_registry, ToolRegistry
from llm.clients import LLMClient


class RegistryCache:
    """
    Singleton cache for tool registry to avoid rebuilding on every agent instantiation.
    
    The registry is built once at startup and reused across all agent instances.
    Only the `query_household_preferences` tool requires an LLM client, so we handle
    that case by creating a separate registry variant when needed.
    """
    
    _instance: Optional[RegistryCache] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> RegistryCache:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
            
        self._project_root: Optional[Path] = None
        self._base_openai_tools: Optional[List[Dict[str, Any]]] = None
        self._base_registry: Optional[ToolRegistry] = None
        self._llm_registry_cache: Dict[str, ToolRegistry] = {}
        self._log = logging.getLogger("moviebot.registry_cache")
        self._initialized = True
    
    def initialize(self, project_root: Path) -> None:
        """
        Initialize the registry cache with the base registry (without LLM client).
        
        This should be called once at application startup.
        """
        if self._project_root is not None:
            self._log.debug("Registry cache already initialized")
            return
            
        self._log.info("Initializing tool registry cache...")
        self._project_root = project_root
        
        # Build base registry without LLM client (most tools don't need it)
        self._base_openai_tools, self._base_registry = build_openai_tools_and_registry(
            project_root, llm_client=None
        )
        
        self._log.info(f"Tool registry cache initialized with {len(self._base_registry._tools)} tools")
    
    def get_registry(self, llm_client: Optional[LLMClient] = None) -> Tuple[List[Dict[str, Any]], ToolRegistry]:
        """
        Get the cached registry, creating an LLM-specific variant if needed.
        
        Args:
            llm_client: Optional LLM client for tools that require it
            
        Returns:
            Tuple of (openai_tools, tool_registry)
        """
        if self._base_registry is None:
            raise RuntimeError("Registry cache not initialized. Call initialize() first.")
        
        # If no LLM client needed, return base registry
        if llm_client is None:
            return self._base_openai_tools, self._base_registry
        
        # For LLM client, check if we have a cached variant
        llm_key = id(llm_client)  # Use object ID as cache key
        if llm_key not in self._llm_registry_cache:
            self._log.debug("Creating LLM-specific registry variant")
            # Build registry with LLM client for tools that need it
            _, llm_registry = build_openai_tools_and_registry(self._project_root, llm_client)
            self._llm_registry_cache[llm_key] = llm_registry
        
        return self._base_openai_tools, self._llm_registry_cache[llm_key]
    
    def is_initialized(self) -> bool:
        """Check if the registry cache has been initialized."""
        return self._base_registry is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            "initialized": self.is_initialized(),
            "base_tools_count": len(self._base_registry._tools) if self._base_registry else 0,
            "llm_variants_count": len(self._llm_registry_cache),
            "project_root": str(self._project_root) if self._project_root else None
        }


# Global singleton instance
_registry_cache = RegistryCache()


def get_registry_cache() -> RegistryCache:
    """Get the global registry cache instance."""
    return _registry_cache


def initialize_registry_cache(project_root: Path) -> None:
    """
    Initialize the global registry cache.
    
    This should be called once at application startup.
    """
    _registry_cache.initialize(project_root)


def get_cached_registry(llm_client: Optional[LLMClient] = None) -> Tuple[List[Dict[str, Any]], ToolRegistry]:
    """
    Get the cached tool registry.
    
    Args:
        llm_client: Optional LLM client for tools that require it
        
    Returns:
        Tuple of (openai_tools, tool_registry)
    """
    return _registry_cache.get_registry(llm_client)
