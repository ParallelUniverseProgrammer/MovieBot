#!/usr/bin/env python3
"""
Test script to validate performance optimizations for Radarr and Plex operations.
"""

import asyncio
import time
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from config.loader import load_settings
from integrations.radarr_client import RadarrClient
from integrations.plex_client import PlexClient, ResponseLevel
from bot.workers.radarr import RadarrWorker
from bot.workers.plex import PlexWorker


async def test_radarr_optimizations():
    """Test Radarr performance optimizations."""
    print("🔧 Testing Radarr Optimizations...")
    
    settings = load_settings(project_root)
    if not settings.radarr_base_url or not settings.radarr_api_key:
        print("  ⚠️  Skipping Radarr tests - configuration missing")
        return
    
    # Test direct client vs worker performance
    client = RadarrClient(settings.radarr_base_url, settings.radarr_api_key)
    worker = RadarrWorker(project_root)
    
    try:
        # Test 1: Direct client performance
        print("  Testing direct client performance...")
        start_time = time.perf_counter()
        
        # Multiple sequential calls
        for i in range(3):
            movies = await client.get_movies()
            print(f"    Call {i+1}: {len(movies)} movies")
        
        direct_time = (time.perf_counter() - start_time) * 1000
        print(f"  Direct client time: {direct_time:.1f}ms")
        
        # Test 2: Worker with caching
        print("  Testing worker with caching...")
        start_time = time.perf_counter()
        
        # First call (cache miss)
        result1 = await worker.get_movies()
        print(f"    First call: {len(result1['movies'])} movies")
        
        # Second call (cache hit)
        result2 = await worker.get_movies()
        print(f"    Second call (cached): {len(result2['movies'])} movies")
        
        worker_time = (time.perf_counter() - start_time) * 1000
        print(f"  Worker time: {worker_time:.1f}ms")
        
        # Test 3: Parallel operations
        print("  Testing parallel operations...")
        start_time = time.perf_counter()
        
        tasks = [worker.get_movies() for _ in range(3)]
        results = await asyncio.gather(*tasks)
        
        parallel_time = (time.perf_counter() - start_time) * 1000
        print(f"  Parallel time: {parallel_time:.1f}ms")
        print(f"  Parallel results: {len(results)} calls completed")
        
    finally:
        await client.close()


async def test_plex_optimizations():
    """Test Plex performance optimizations."""
    print("\n🔧 Testing Plex Optimizations...")
    
    settings = load_settings(project_root)
    if not settings.plex_base_url or not settings.plex_token:
        print("  ⚠️  Skipping Plex tests - configuration missing")
        return
    
    # Test direct client vs worker performance
    client = PlexClient(settings.plex_base_url, settings.plex_token, ResponseLevel.COMPACT)
    worker = PlexWorker(project_root)
    
    try:
        # Test 1: Direct client unwatched performance
        print("  Testing direct client unwatched performance...")
        start_time = time.perf_counter()
        
        # Multiple sequential calls
        for i in range(3):
            unwatched = client.get_unwatched("movie", 10)
            print(f"    Call {i+1}: {len(unwatched)} unwatched movies")
        
        direct_time = (time.perf_counter() - start_time) * 1000
        print(f"  Direct client time: {direct_time:.1f}ms")
        
        # Test 2: Worker with caching and coalescing
        print("  Testing worker with caching and coalescing...")
        start_time = time.perf_counter()
        
        # First call (cache miss)
        result1 = await worker.get_unwatched(section_type="movie", limit=10, response_level="compact")
        print(f"    First call: {len(result1['items'])} unwatched movies")
        
        # Second call (cache hit)
        result2 = await worker.get_unwatched(section_type="movie", limit=10, response_level="compact")
        print(f"    Second call (cached): {len(result2['items'])} unwatched movies")
        
        worker_time = (time.perf_counter() - start_time) * 1000
        print(f"  Worker time: {worker_time:.1f}ms")
        
        # Test 3: Parallel operations with coalescing
        print("  Testing parallel operations with coalescing...")
        start_time = time.perf_counter()
        
        tasks = [
            worker.get_unwatched(section_type="movie", limit=10, response_level="compact")
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks)
        
        parallel_time = (time.perf_counter() - start_time) * 1000
        print(f"  Parallel time: {parallel_time:.1f}ms")
        print(f"  Parallel results: {len(results)} calls completed")
        
        # Test 4: New library overview optimization
        print("  Testing library overview optimization...")
        start_time = time.perf_counter()
        
        overview = await worker.get_library_overview(response_level="compact")
        
        overview_time = (time.perf_counter() - start_time) * 1000
        print(f"  Library overview time: {overview_time:.1f}ms")
        print(f"  Overview contains: {list(overview.keys())}")
        
    except Exception as e:
        print(f"  ❌ Plex test failed: {e}")


async def test_connection_pooling():
    """Test HTTP connection pooling benefits."""
    print("\n🔧 Testing Connection Pooling...")
    
    settings = load_settings(project_root)
    if not settings.radarr_base_url or not settings.radarr_api_key:
        print("  ⚠️  Skipping connection pooling tests - Radarr configuration missing")
        return
    
    # Test with persistent client (new optimization)
    client = RadarrClient(settings.radarr_base_url, settings.radarr_api_key)
    
    try:
        print("  Testing persistent client with connection pooling...")
        start_time = time.perf_counter()
        
        # Multiple API calls using the same client
        tasks = [
            client.get_movies(),
            client.system_status(),
            client.quality_profiles(),
            client.root_folders(),
        ]
        
        results = await asyncio.gather(*tasks)
        
        persistent_time = (time.perf_counter() - start_time) * 1000
        print(f"  Persistent client time: {persistent_time:.1f}ms")
        print(f"  Results: {len(results)} API calls completed")
        
    finally:
        await client.close()


async def main():
    """Run all optimization tests."""
    print("🚀 MovieBot Performance Optimization Tests")
    print("=" * 50)
    
    await test_radarr_optimizations()
    await test_plex_optimizations()
    await test_connection_pooling()
    
    print("\n✅ Optimization tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
