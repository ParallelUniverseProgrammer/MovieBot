#!/usr/bin/env python3
"""
Performance profiling script for MovieBot agent.
Runs multiple test queries with detailed timing analysis.
"""

import asyncio
import subprocess
import time
import json
from pathlib import Path
from typing import List, Dict, Any

# Test queries of varying complexity
SIMPLE_QUERIES = [
    "Add The Matrix (1999) to my Radarr",
    "Show me my Plex library",
    "What's trending on TMDb?",
]

COMPLEX_QUERIES = [
    "Show me all the horror movies in my Plex library from 2020-2023, sorted by rating, and tell me which ones I haven't watched yet",
    "Find all sci-fi movies from the 80s that are available on TMDb, check if I have them in Plex, and add any missing ones to Radarr",
    "Analyze my Plex library and recommend 5 movies I should watch based on my viewing history and current trends",
]

async def run_profiled_query(query: str, profile: bool = True) -> Dict[str, Any]:
    """Run a single query with profiling enabled."""
    script_path = Path(__file__).parent / "trace_agent.py"
    
    cmd = [
        "python", str(script_path),
        "--message", query,
        "--max-events", "50"
    ]
    
    if profile:
        cmd.append("--profile")
    
    start_time = time.perf_counter()
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        end_time = time.perf_counter()
        total_time = end_time - start_time
        
        return {
            "query": query,
            "success": result.returncode == 0,
            "total_time": total_time,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "query": query,
            "success": False,
            "total_time": 120.0,
            "error": "timeout",
            "stdout": "",
            "stderr": "Query timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "query": query,
            "success": False,
            "total_time": time.perf_counter() - start_time,
            "error": str(e),
            "stdout": "",
            "stderr": str(e)
        }

async def run_performance_benchmark():
    """Run comprehensive performance benchmark."""
    print("🚀 Starting MovieBot Performance Benchmark")
    print("=" * 60)
    
    results = []
    
    # Test simple queries
    print("\n📊 Testing Simple Queries...")
    for i, query in enumerate(SIMPLE_QUERIES, 1):
        print(f"\n[{i}/{len(SIMPLE_QUERIES)}] Simple Query: {query[:50]}...")
        result = await run_profiled_query(query)
        results.append({**result, "complexity": "simple"})
        
        if result["success"]:
            print(f"✅ Completed in {result['total_time']:.2f}s")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
    
    # Test complex queries
    print("\n📊 Testing Complex Queries...")
    for i, query in enumerate(COMPLEX_QUERIES, 1):
        print(f"\n[{i}/{len(COMPLEX_QUERIES)}] Complex Query: {query[:50]}...")
        result = await run_profiled_query(query)
        results.append({**result, "complexity": "complex"})
        
        if result["success"]:
            print(f"✅ Completed in {result['total_time']:.2f}s")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
    
    # Analyze results
    print("\n" + "=" * 60)
    print("📈 PERFORMANCE ANALYSIS")
    print("=" * 60)
    
    simple_results = [r for r in results if r["complexity"] == "simple" and r["success"]]
    complex_results = [r for r in results if r["complexity"] == "complex" and r["success"]]
    
    if simple_results:
        simple_times = [r["total_time"] for r in simple_results]
        print(f"\nSimple Queries ({len(simple_results)} successful):")
        print(f"  Average: {sum(simple_times)/len(simple_times):.2f}s")
        print(f"  Min: {min(simple_times):.2f}s")
        print(f"  Max: {max(simple_times):.2f}s")
    
    if complex_results:
        complex_times = [r["total_time"] for r in complex_results]
        print(f"\nComplex Queries ({len(complex_results)} successful):")
        print(f"  Average: {sum(complex_times)/len(complex_times):.2f}s")
        print(f"  Min: {min(complex_times):.2f}s")
        print(f"  Max: {max(complex_times):.2f}s")
    
    # Performance targets
    print(f"\n🎯 Performance Targets:")
    print(f"  Target: <5.0s (all queries)")
    print(f"  Stretch: <2.0s (all queries)")
    
    # Check against targets
    all_times = [r["total_time"] for r in results if r["success"]]
    if all_times:
        target_met = all(t < 5.0 for t in all_times)
        stretch_met = all(t < 2.0 for t in all_times)
        
        print(f"\n📊 Results:")
        print(f"  Target Met (<5s): {'✅' if target_met else '❌'}")
        print(f"  Stretch Met (<2s): {'✅' if stretch_met else '❌'}")
        
        if not target_met:
            slow_queries = [r for r in results if r["success"] and r["total_time"] >= 5.0]
            print(f"\n⚠️  Slow Queries (≥5s):")
            for r in slow_queries:
                print(f"    {r['total_time']:.2f}s: {r['query'][:60]}...")
    
    # Save detailed results
    results_file = Path("performance_benchmark_results.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {results_file}")
    print("\n🔍 To analyze individual query performance, run:")
    print("   python scripts/trace_agent.py --profile --message 'your query here'")

if __name__ == "__main__":
    asyncio.run(run_performance_benchmark())
