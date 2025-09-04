#!/usr/bin/env python3
"""
MovieBot Performance Benchmarking Tool

This script comprehensively benchmarks all MovieBot integrations and operations
to measure performance, identify bottlenecks, and ensure optimal operation.

Features:
- Individual API call timing
- End-to-end operation timing  
- Sequential vs parallel performance comparison
- Agent query benchmarking via trace_agent.py integration
- Configurable iteration counts with statistical analysis
- Performance threshold monitoring (warns on >1000ms operations)
- Service-specific filtering options
"""

from __future__ import annotations

import asyncio
import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import subprocess
import tempfile
import os

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_settings, load_runtime_config, is_config_complete


@dataclass
class BenchmarkResult:
    """Individual benchmark result with timing and metadata."""
    operation: str
    service: str
    duration_ms: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results for a specific test suite."""
    name: str
    results: List[BenchmarkResult] = field(default_factory=list)
    iterations: int = 1
    
    def add_result(self, result: BenchmarkResult) -> None:
        """Add a benchmark result to this suite."""
        self.results.append(result)
    
    def get_stats(self) -> Dict[str, Any]:
        """Calculate statistics for this benchmark suite."""
        if not self.results:
            return {}
        
        durations = [r.duration_ms for r in self.results if r.success]
        if not durations:
            return {"success_count": 0, "failure_count": len(self.results)}
        
        return {
            "success_count": len(durations),
            "failure_count": len(self.results) - len(durations),
            "mean_ms": round(statistics.mean(durations), 2),
            "median_ms": round(statistics.median(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "stdev_ms": round(statistics.stdev(durations) if len(durations) > 1 else 0, 2),
        }


class PerformanceBenchmarker:
    """Main benchmarking orchestrator."""
    
    def __init__(self, project_root: Path, iterations: int = 3, verbose: bool = False):
        self.project_root = project_root
        self.iterations = iterations
        self.verbose = verbose
        self.suites: Dict[str, BenchmarkSuite] = {}
        self.settings = load_settings(project_root)
        self.config = load_runtime_config(project_root)
        self.slow_threshold_ms = 1000.0
        # Agent-specific thresholds (in milliseconds)
        self.agent_simple_threshold_ms = 30000.0  # 30 seconds for simple queries
        self.agent_complex_threshold_ms = 60000.0  # 1 minute for complex queries
        self._cleanup_tasks = []
        
    def create_suite(self, name: str) -> BenchmarkSuite:
        """Create a new benchmark suite."""
        suite = BenchmarkSuite(name=name, iterations=self.iterations)
        self.suites[name] = suite
        return suite
    
    def is_agent_query_simple(self, query: str) -> bool:
        """Determine if an agent query is simple based on complexity heuristics."""
        word_count = len(query.split())
        has_filters = any(word in query.lower() for word in ['with', 'above', 'below', 'from', 'to', 'that', 'similar'])
        has_multiple_conditions = query.count('and') + query.count('but') + query.count('or') > 0
        
        return word_count <= 5 and not has_filters and not has_multiple_conditions
    
    def get_agent_threshold(self, query: str) -> float:
        """Get the appropriate threshold for an agent query based on complexity."""
        if self.is_agent_query_simple(query):
            return self.agent_simple_threshold_ms
        else:
            return self.agent_complex_threshold_ms
    
    async def time_operation(self, operation_name: str, service: str, func, *args, **kwargs) -> BenchmarkResult:
        """Time a single operation and return the result."""
        start_time = time.perf_counter()
        success = True
        error = None
        metadata = {}
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            metadata["result_type"] = type(result).__name__
            if isinstance(result, dict):
                metadata["result_keys"] = list(result.keys())
        except Exception as e:
            success = False
            error = str(e)
            result = None
        
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        
        return BenchmarkResult(
            operation=operation_name,
            service=service,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata
        )
    
    def print_result(self, result: BenchmarkResult) -> None:
        """Print a single benchmark result with appropriate formatting."""
        status = "✅" if result.success else "❌"
        duration_str = f"{result.duration_ms:.1f}ms"
        
        # Determine threshold based on service and query complexity
        threshold = self.slow_threshold_ms
        if result.service == "Agent" and "query" in result.metadata:
            threshold = self.get_agent_threshold(result.metadata["query"])
        
        # Add warning for slow operations
        if result.success and result.duration_ms > threshold:
            duration_str += " ⚠️ SLOW"
            if result.service == "Agent":
                complexity = "simple" if self.is_agent_query_simple(result.metadata.get("query", "")) else "complex"
                duration_str += f" (exceeds {complexity} agent threshold)"
        
        print(f"  {status} {result.operation}: {duration_str}")
        
        if not result.success and self.verbose:
            print(f"    Error: {result.error}")
        
        if self.verbose and result.metadata:
            print(f"    Metadata: {result.metadata}")
    
    def print_suite_summary(self, suite: BenchmarkSuite) -> None:
        """Print summary statistics for a benchmark suite."""
        stats = suite.get_stats()
        if not stats:
            print(f"\n📊 {suite.name}: No successful results")
            return
        
        print(f"\n📊 {suite.name} Summary:")
        print(f"  Success: {stats['success_count']}/{stats['success_count'] + stats['failure_count']}")
        
        if stats['success_count'] > 0:
            print(f"  Timing: {stats['mean_ms']:.1f}ms avg, {stats['min_ms']:.1f}ms-{stats['max_ms']:.1f}ms range")
            if stats['stdev_ms'] > 0:
                print(f"  Variability: ±{stats['stdev_ms']:.1f}ms std dev")
            
            # Determine appropriate threshold for this suite
            threshold = self.slow_threshold_ms
            if "Agent" in suite.name:
                # For agent suites, use the higher threshold (complex queries)
                threshold = self.agent_complex_threshold_ms
            
            # Flag slow operations
            if stats['mean_ms'] > threshold:
                if "Agent" in suite.name:
                    print(f"  ⚠️  WARNING: Average time exceeds {threshold/1000:.0f}s agent threshold")
                else:
                    print(f"  ⚠️  WARNING: Average time exceeds {threshold}ms threshold")
    
    async def run_benchmark_suite(self, suite_name: str, operations: List[Tuple[str, str, callable, tuple, dict]]) -> None:
        """Run a suite of benchmark operations."""
        suite = self.create_suite(suite_name)
        
        print(f"\n🔍 Running {suite_name} benchmarks...")
        
        for iteration in range(self.iterations):
            if self.iterations > 1:
                print(f"\n  Iteration {iteration + 1}/{self.iterations}:")
            
            for op_name, service, func, args, kwargs in operations:
                result = await self.time_operation(op_name, service, func, *args, **kwargs)
                suite.add_result(result)
                self.print_result(result)
        
        self.print_suite_summary(suite)
    
    async def cleanup(self) -> None:
        """Clean up any resources used during benchmarking."""
        # Close any HTTP clients or other resources
        for task in self._cleanup_tasks:
            try:
                if hasattr(task, 'close'):
                    await task.close()
            except Exception:
                pass
        self._cleanup_tasks.clear()


def build_argparser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Comprehensive MovieBot performance benchmarking tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all benchmarks with default settings
  python scripts/benchmark_performance.py
  
  # Run only Plex benchmarks with 5 iterations
  python scripts/benchmark_performance.py --plex-only --iterations 5
  
  # Run with verbose output
  python scripts/benchmark_performance.py --verbose
  
  # Run agent benchmarks with custom thresholds
  python scripts/benchmark_performance.py --agent-only --agent-simple-threshold 45 --agent-complex-threshold 90
  
  # Run specific service benchmarks
  python scripts/benchmark_performance.py --radarr-only --sonarr-only
        """
    )
    
    # Service selection
    parser.add_argument("--plex-only", action="store_true", help="Run only Plex benchmarks")
    parser.add_argument("--radarr-only", action="store_true", help="Run only Radarr benchmarks")
    parser.add_argument("--sonarr-only", action="store_true", help="Run only Sonarr benchmarks")
    parser.add_argument("--tmdb-only", action="store_true", help="Run only TMDb benchmarks")
    parser.add_argument("--agent-only", action="store_true", help="Run only agent benchmarks")
    
    # Benchmark configuration
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations per test (default: 3)")
    parser.add_argument("--threshold", type=float, default=1000.0, help="Slow operation threshold in ms (default: 1000)")
    parser.add_argument("--agent-simple-threshold", type=float, default=30.0, help="Agent simple query threshold in seconds (default: 30)")
    parser.add_argument("--agent-complex-threshold", type=float, default=60.0, help="Agent complex query threshold in seconds (default: 60)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output with detailed metadata")
    
    # Test selection
    parser.add_argument("--skip-connectivity", action="store_true", help="Skip basic connectivity tests")
    parser.add_argument("--skip-search", action="store_true", help="Skip search operation tests")
    parser.add_argument("--skip-metadata", action="store_true", help="Skip metadata retrieval tests")
    parser.add_argument("--skip-agent", action="store_true", help="Skip agent integration tests")
    parser.add_argument("--skip-tools", action="store_true", help="Skip tool implementation tests")
    parser.add_argument("--skip-workers", action="store_true", help="Skip worker integration tests")
    
    return parser


async def validate_environment(benchmarker: PerformanceBenchmarker) -> bool:
    """Validate that the environment is properly configured for benchmarking."""
    print("  Checking configuration completeness...")
    
    # Check if config is complete using the same logic as main bot
    if not is_config_complete(benchmarker.settings, benchmarker.config):
        print("  ❌ Configuration incomplete - missing required settings")
        return False
    
    # Check for required API keys based on what we plan to test
    required_keys = []
    
    # Always need at least one LLM provider
    if not benchmarker.settings.openai_api_key and not benchmarker.settings.openrouter_api_key:
        required_keys.append("OPENAI_API_KEY or OPENROUTER_API_KEY")
    
    # Check service-specific requirements
    if benchmarker.settings.plex_base_url and benchmarker.settings.plex_token:
        print("  ✅ Plex configuration found")
    else:
        print("  ⚠️  Plex configuration missing (will skip Plex tests)")
    
    if benchmarker.settings.radarr_base_url and benchmarker.settings.radarr_api_key:
        print("  ✅ Radarr configuration found")
    else:
        print("  ⚠️  Radarr configuration missing (will skip Radarr tests)")
    
    if benchmarker.settings.sonarr_base_url and benchmarker.settings.sonarr_api_key:
        print("  ✅ Sonarr configuration found")
    else:
        print("  ⚠️  Sonarr configuration missing (will skip Sonarr tests)")
    
    if benchmarker.settings.tmdb_api_key:
        print("  ✅ TMDb configuration found")
    else:
        print("  ⚠️  TMDb configuration missing (will skip TMDb tests)")
    
    if required_keys:
        print(f"  ❌ Missing required keys: {', '.join(required_keys)}")
        return False
    
    print("  ✅ Environment validation passed")
    return True


async def run_plex_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run Plex-specific benchmarks."""
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print("  ⚠️  Skipping Plex benchmarks - configuration missing")
        return
    
    from integrations.plex_client import PlexClient, ResponseLevel
    
    # Initialize Plex client
    plex_client = PlexClient(
        benchmarker.settings.plex_base_url,
        benchmarker.settings.plex_token,
        default_response_level=ResponseLevel.COMPACT
    )
    
    try:
        # Basic connectivity and status operations
        if not args.skip_connectivity:
            connectivity_ops = [
                ("Plex Server Status", "Plex", plex_client.get_quick_status, (), {}),
                ("Library Sections", "Plex", plex_client.get_library_sections, (), {}),
                ("Movie Library Access", "Plex", plex_client.get_movie_library, (), {}),
                ("TV Library Access", "Plex", plex_client.get_tv_library, (), {}),
            ]
            await benchmarker.run_benchmark_suite("Plex Connectivity", connectivity_ops)
        
        # Search operations
        if not args.skip_search:
            search_ops = [
                ("Search Movies - 'inception'", "Plex", plex_client.search_movies, ("inception",), {"response_level": ResponseLevel.COMPACT}),
                ("Search Shows - 'office'", "Plex", plex_client.search_shows, ("office",), {"response_level": ResponseLevel.COMPACT}),
                ("Search All - 'matrix'", "Plex", plex_client.search_all, ("matrix",), {"response_level": ResponseLevel.COMPACT}),
                ("Search Movies - 'pirates'", "Plex", plex_client.search_movies, ("pirates",), {"response_level": ResponseLevel.STANDARD}),
            ]
            await benchmarker.run_benchmark_suite("Plex Search Operations", search_ops)
        
        # Metadata retrieval operations
        if not args.skip_metadata:
            # Get some items first for detailed operations
            try:
                movies = plex_client.search_movies("inception", response_level=ResponseLevel.COMPACT)
                shows = plex_client.search_shows("office", response_level=ResponseLevel.COMPACT)
                
                metadata_ops = []
                
                # Add movie detail operations if we found movies
                if movies and len(movies) > 0:
                    first_movie = movies[0]
                    if hasattr(first_movie, 'ratingKey'):
                        metadata_ops.append(("Movie Details", "Plex", plex_client.get_item_details, (first_movie.ratingKey,), {"response_level": ResponseLevel.DETAILED}))
                
                # Add show detail operations if we found shows
                if shows and len(shows) > 0:
                    first_show = shows[0]
                    if hasattr(first_show, 'ratingKey'):
                        metadata_ops.append(("Show Details", "Plex", plex_client.get_item_details, (first_show.ratingKey,), {"response_level": ResponseLevel.DETAILED}))
                
                # Add library enumeration operations
                metadata_ops.extend([
                    ("Recently Added Movies", "Plex", plex_client.get_recently_added, ("movie",), {"limit": 10, "response_level": ResponseLevel.COMPACT}),
                    ("Recently Added Shows", "Plex", plex_client.get_recently_added, ("show",), {"limit": 10, "response_level": ResponseLevel.COMPACT}),
                    ("On Deck Items", "Plex", plex_client.get_on_deck, (), {"limit": 10, "response_level": ResponseLevel.COMPACT}),
                ])
                
                if metadata_ops:
                    await benchmarker.run_benchmark_suite("Plex Metadata Operations", metadata_ops)
                else:
                    print("  ⚠️  Skipping metadata operations - no items found for detailed testing")
                    
            except Exception as e:
                print(f"  ⚠️  Skipping metadata operations - error getting test items: {e}")
        
        # Sequential vs Parallel comparison
        if not args.skip_connectivity and not args.skip_search:
            await run_plex_parallel_comparison(benchmarker, plex_client)
            
    except Exception as e:
        print(f"  ❌ Plex benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        try:
            await plex_client.close()
        except Exception:
            pass


async def run_plex_parallel_comparison(benchmarker: PerformanceBenchmarker, plex_client) -> None:
    """Compare sequential vs parallel Plex operations."""
    from integrations.plex_client import ResponseLevel
    
    print("\n🔄 Running Plex Sequential vs Parallel Comparison...")
    
    # Define operations to test
    operations = [
        ("Search Movies 1", plex_client.search_movies, ("inception",), {"response_level": ResponseLevel.COMPACT}),
        ("Search Movies 2", plex_client.search_movies, ("matrix",), {"response_level": ResponseLevel.COMPACT}),
        ("Search Shows 1", plex_client.search_shows, ("office",), {"response_level": ResponseLevel.COMPACT}),
        ("Search Shows 2", plex_client.search_shows, ("breaking",), {"response_level": ResponseLevel.COMPACT}),
    ]
    
    # Sequential execution
    suite = benchmarker.create_suite("Plex Sequential Operations")
    start_time = time.perf_counter()
    
    for op_name, func, args, kwargs in operations:
        result = await benchmarker.time_operation(op_name, "Plex", func, *args, **kwargs)
        suite.add_result(result)
        benchmarker.print_result(result)
    
    sequential_time = (time.perf_counter() - start_time) * 1000
    
    # Parallel execution
    suite = benchmarker.create_suite("Plex Parallel Operations")
    start_time = time.perf_counter()
    
    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "Plex", func, *args, **kwargs)
    
    tasks = [run_operation(op_name, func, args, kwargs) for op_name, func, args, kwargs in operations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    parallel_time = (time.perf_counter() - start_time) * 1000
    
    for result in results:
        if isinstance(result, BenchmarkResult):
            suite.add_result(result)
            benchmarker.print_result(result)
        else:
            print(f"  ❌ Parallel operation failed: {result}")
    
    # Print comparison
    print(f"\n📊 Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time: {parallel_time:.1f}ms")
    if sequential_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  ✅ Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  ⚠️  Parallel execution shows modest improvement")
        else:
            print(f"  ⚠️  Parallel execution shows minimal improvement")
    
    benchmarker.print_suite_summary(suite)


async def run_radarr_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run Radarr-specific benchmarks."""
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print("  ⚠️  Skipping Radarr benchmarks - configuration missing")
        return
    
    from integrations.radarr_client import RadarrClient
    
    # Initialize Radarr client
    radarr_client = RadarrClient(
        benchmarker.settings.radarr_base_url,
        benchmarker.settings.radarr_api_key
    )
    
    try:
        # Basic connectivity and system operations
        if not args.skip_connectivity:
            connectivity_ops = [
                ("System Status", "Radarr", radarr_client.system_status, (), {}),
                ("Quality Profiles", "Radarr", radarr_client.quality_profiles, (), {}),
                ("Root Folders", "Radarr", radarr_client.root_folders, (), {}),
            ]
            await benchmarker.run_benchmark_suite("Radarr Connectivity", connectivity_ops)
        
        # Movie management operations (read-only)
        if not args.skip_search:
            search_ops = [
                ("Get All Movies", "Radarr", radarr_client.get_movies, (), {}),
                ("Get Movie Queue", "Radarr", radarr_client.get_queue, (), {}),
                ("Get Movie History", "Radarr", radarr_client.get_history, (), {"page_size": 10}),
                ("Get Wanted Missing", "Radarr", radarr_client.get_wanted, (), {"page_size": 10}),
            ]
            await benchmarker.run_benchmark_suite("Radarr Movie Operations", search_ops)
        
        # Metadata and configuration operations
        if not args.skip_metadata:
            metadata_ops = [
                ("Get Indexers", "Radarr", radarr_client.get_indexers, (), {}),
                ("Get Download Clients", "Radarr", radarr_client.get_download_clients, (), {}),
                ("Get Notifications", "Radarr", radarr_client.get_notifications, (), {}),
                ("Get Tags", "Radarr", radarr_client.get_tags, (), {}),
            ]
            await benchmarker.run_benchmark_suite("Radarr Configuration", metadata_ops)
        
        # Sequential vs Parallel comparison
        if not args.skip_connectivity and not args.skip_search:
            await run_radarr_parallel_comparison(benchmarker, radarr_client)
            
    except Exception as e:
        print(f"  ❌ Radarr benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        try:
            await radarr_client.close()
        except Exception:
            pass


async def run_radarr_parallel_comparison(benchmarker: PerformanceBenchmarker, radarr_client) -> None:
    """Compare sequential vs parallel Radarr operations."""
    print("\n🔄 Running Radarr Sequential vs Parallel Comparison...")
    
    # Define operations to test
    operations = [
        ("System Status", radarr_client.system_status, (), {}),
        ("Quality Profiles", radarr_client.quality_profiles, (), {}),
        ("Root Folders", radarr_client.root_folders, (), {}),
        ("Get Movies", radarr_client.get_movies, (), {}),
    ]
    
    # Sequential execution
    suite = benchmarker.create_suite("Radarr Sequential Operations")
    start_time = time.perf_counter()
    
    for op_name, func, args, kwargs in operations:
        result = await benchmarker.time_operation(op_name, "Radarr", func, *args, **kwargs)
        suite.add_result(result)
        benchmarker.print_result(result)
    
    sequential_time = (time.perf_counter() - start_time) * 1000
    
    # Parallel execution
    suite = benchmarker.create_suite("Radarr Parallel Operations")
    start_time = time.perf_counter()
    
    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "Radarr", func, *args, **kwargs)
    
    tasks = [run_operation(op_name, func, args, kwargs) for op_name, func, args, kwargs in operations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    parallel_time = (time.perf_counter() - start_time) * 1000
    
    for result in results:
        if isinstance(result, BenchmarkResult):
            suite.add_result(result)
            benchmarker.print_result(result)
        else:
            print(f"  ❌ Parallel operation failed: {result}")
    
    # Print comparison
    print(f"\n📊 Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time: {parallel_time:.1f}ms")
    if sequential_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  ✅ Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  ⚠️  Parallel execution shows modest improvement")
        else:
            print(f"  ⚠️  Parallel execution shows minimal improvement")
    
    benchmarker.print_suite_summary(suite)


async def run_sonarr_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run Sonarr-specific benchmarks."""
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print("  ⚠️  Skipping Sonarr benchmarks - configuration missing")
        return
    
    from integrations.sonarr_client import SonarrClient
    
    # Initialize Sonarr client
    sonarr_client = SonarrClient(
        benchmarker.settings.sonarr_base_url,
        benchmarker.settings.sonarr_api_key
    )
    
    try:
        # Basic connectivity and system operations
        if not args.skip_connectivity:
            connectivity_ops = [
                ("System Status", "Sonarr", sonarr_client.system_status, (), {}),
                ("Quality Profiles", "Sonarr", sonarr_client.quality_profiles, (), {}),
                ("Root Folders", "Sonarr", sonarr_client.root_folders, (), {}),
            ]
            await benchmarker.run_benchmark_suite("Sonarr Connectivity", connectivity_ops)
        
        # TV show management operations (read-only)
        if not args.skip_search:
            search_ops = [
                ("Get All Series", "Sonarr", sonarr_client.get_series, (), {}),
                ("Get Episode Queue", "Sonarr", sonarr_client.get_queue, (), {}),
                ("Get Episode History", "Sonarr", sonarr_client.get_history, (), {"page_size": 10}),
                ("Get Wanted Missing", "Sonarr", sonarr_client.get_wanted, (), {"page_size": 10}),
            ]
            await benchmarker.run_benchmark_suite("Sonarr Series Operations", search_ops)
        
        # Metadata and configuration operations
        if not args.skip_metadata:
            metadata_ops = [
                ("Get Import Lists", "Sonarr", sonarr_client.get_import_lists, (), {}),
                ("Get Notifications", "Sonarr", sonarr_client.get_notifications, (), {}),
                ("Get Tags", "Sonarr", sonarr_client.get_tags, (), {}),
                ("Get Calendar", "Sonarr", sonarr_client.get_calendar, (), {}),
            ]
            await benchmarker.run_benchmark_suite("Sonarr Configuration", metadata_ops)
        
        # Sequential vs Parallel comparison
        if not args.skip_connectivity and not args.skip_search:
            await run_sonarr_parallel_comparison(benchmarker, sonarr_client)
            
    except Exception as e:
        print(f"  ❌ Sonarr benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        try:
            await sonarr_client.close()
        except Exception:
            pass


async def run_sonarr_parallel_comparison(benchmarker: PerformanceBenchmarker, sonarr_client) -> None:
    """Compare sequential vs parallel Sonarr operations."""
    print("\n🔄 Running Sonarr Sequential vs Parallel Comparison...")
    
    # Define operations to test
    operations = [
        ("System Status", sonarr_client.system_status, (), {}),
        ("Quality Profiles", sonarr_client.quality_profiles, (), {}),
        ("Root Folders", sonarr_client.root_folders, (), {}),
        ("Get Series", sonarr_client.get_series, (), {}),
    ]
    
    # Sequential execution
    suite = benchmarker.create_suite("Sonarr Sequential Operations")
    start_time = time.perf_counter()
    
    for op_name, func, args, kwargs in operations:
        result = await benchmarker.time_operation(op_name, "Sonarr", func, *args, **kwargs)
        suite.add_result(result)
        benchmarker.print_result(result)
    
    sequential_time = (time.perf_counter() - start_time) * 1000
    
    # Parallel execution
    suite = benchmarker.create_suite("Sonarr Parallel Operations")
    start_time = time.perf_counter()
    
    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "Sonarr", func, *args, **kwargs)
    
    tasks = [run_operation(op_name, func, args, kwargs) for op_name, func, args, kwargs in operations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    parallel_time = (time.perf_counter() - start_time) * 1000
    
    for result in results:
        if isinstance(result, BenchmarkResult):
            suite.add_result(result)
            benchmarker.print_result(result)
        else:
            print(f"  ❌ Parallel operation failed: {result}")
    
    # Print comparison
    print(f"\n📊 Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time: {parallel_time:.1f}ms")
    if sequential_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  ✅ Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  ⚠️  Parallel execution shows modest improvement")
        else:
            print(f"  ⚠️  Parallel execution shows minimal improvement")
    
    benchmarker.print_suite_summary(suite)


async def run_tmdb_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run TMDb-specific benchmarks."""
    if not benchmarker.settings.tmdb_api_key:
        print("  ⚠️  Skipping TMDb benchmarks - configuration missing")
        return
    
    from integrations.tmdb_client import TMDbClient, TMDbResponseLevel
    
    # Initialize TMDb client
    tmdb_client = TMDbClient(benchmarker.settings.tmdb_api_key)
    
    try:
        # Basic search and discovery operations
        if not args.skip_search:
            search_ops = [
                ("Search Movies - 'inception'", "TMDb", tmdb_client.search_movie, ("inception",), {"response_level": TMDbResponseLevel.COMPACT}),
                ("Search Movies - 'matrix'", "TMDb", tmdb_client.search_movie, ("matrix",), {"response_level": TMDbResponseLevel.STANDARD}),
                ("Search TV Shows - 'office'", "TMDb", tmdb_client.search_tv, ("office",), {"response_level": TMDbResponseLevel.COMPACT}),
                ("Search People - 'tom hanks'", "TMDb", tmdb_client.search_person, ("tom hanks",), {"response_level": TMDbResponseLevel.COMPACT}),
            ]
            await benchmarker.run_benchmark_suite("TMDb Search Operations", search_ops)
        
        # Discovery and trending operations
        if not args.skip_metadata:
            discovery_ops = [
                ("Popular Movies", "TMDb", tmdb_client.popular_movies, (), {"response_level": TMDbResponseLevel.COMPACT}),
                ("Top Rated Movies", "TMDb", tmdb_client.top_rated_movies, (), {"response_level": TMDbResponseLevel.COMPACT}),
                ("Now Playing Movies", "TMDb", tmdb_client.now_playing_movies, (), {"response_level": TMDbResponseLevel.COMPACT}),
                ("Popular TV Shows", "TMDb", tmdb_client.popular_tv, (), {"response_level": TMDbResponseLevel.COMPACT}),
            ]
            await benchmarker.run_benchmark_suite("TMDb Discovery Operations", discovery_ops)
        
        # Sequential vs Parallel comparison
        if not args.skip_search and not args.skip_metadata:
            await run_tmdb_parallel_comparison(benchmarker, tmdb_client)
            
    except Exception as e:
        print(f"  ❌ TMDb benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    finally:
        try:
            await tmdb_client.close()
        except Exception:
            pass


async def run_tmdb_parallel_comparison(benchmarker: PerformanceBenchmarker, tmdb_client) -> None:
    """Compare sequential vs parallel TMDb operations."""
    from integrations.tmdb_client import TMDbResponseLevel
    
    print("\n🔄 Running TMDb Sequential vs Parallel Comparison...")
    
    # Define operations to test
    operations = [
        ("Search Movies 1", tmdb_client.search_movie, ("inception",), {"response_level": TMDbResponseLevel.COMPACT}),
        ("Search Movies 2", tmdb_client.search_movie, ("matrix",), {"response_level": TMDbResponseLevel.COMPACT}),
        ("Popular Movies", tmdb_client.popular_movies, (), {"response_level": TMDbResponseLevel.COMPACT}),
        ("Top Rated Movies", tmdb_client.top_rated_movies, (), {"response_level": TMDbResponseLevel.COMPACT}),
    ]
    
    # Sequential execution
    suite = benchmarker.create_suite("TMDb Sequential Operations")
    start_time = time.perf_counter()
    
    for op_name, func, args, kwargs in operations:
        result = await benchmarker.time_operation(op_name, "TMDb", func, *args, **kwargs)
        suite.add_result(result)
        benchmarker.print_result(result)
    
    sequential_time = (time.perf_counter() - start_time) * 1000
    
    # Parallel execution
    suite = benchmarker.create_suite("TMDb Parallel Operations")
    start_time = time.perf_counter()
    
    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "TMDb", func, *args, **kwargs)
    
    tasks = [run_operation(op_name, func, args, kwargs) for op_name, func, args, kwargs in operations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    parallel_time = (time.perf_counter() - start_time) * 1000
    
    for result in results:
        if isinstance(result, BenchmarkResult):
            suite.add_result(result)
            benchmarker.print_result(result)
        else:
            print(f"  ❌ Parallel operation failed: {result}")
    
    # Print comparison
    print(f"\n📊 Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time: {parallel_time:.1f}ms")
    if sequential_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  ✅ Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  ⚠️  Parallel execution shows modest improvement")
        else:
            print(f"  ⚠️  Parallel execution shows minimal improvement")
    
    benchmarker.print_suite_summary(suite)


async def run_agent_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run agent integration benchmarks using trace_agent.py."""
    if not benchmarker.settings.openai_api_key and not benchmarker.settings.openrouter_api_key:
        print("  ⚠️  Skipping agent benchmarks - no LLM API key configured")
        return
    
    print("  🤖 Running agent integration benchmarks...")
    
    # Define test queries for different complexity levels
    simple_queries = [
        "Show me recent movies",
        "What's on deck in Plex?",
        "List my unwatched movies",
        "Search for Inception",
    ]
    
    complex_queries = [
        "Find me horror movies from 2020-2023 with rating above 7.0",
        "Show me all the action movies in my Plex library that I haven't watched yet",
        "Recommend something similar to The Matrix but more recent",
        "What are the most popular movies from 2023 that I don't have?",
    ]
    
    try:
        # Simple agent queries
        if not args.skip_search:
            await run_agent_query_suite(benchmarker, "Simple Agent Queries", simple_queries)
        
        # Complex agent queries
        if not args.skip_metadata:
            await run_agent_query_suite(benchmarker, "Complex Agent Queries", complex_queries)
        
        # Agent performance comparison
        if not args.skip_search and not args.skip_metadata:
            await run_agent_performance_comparison(benchmarker, simple_queries + complex_queries)
            
    except Exception as e:
        print(f"  ❌ Agent benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


async def run_agent_query_suite(benchmarker: PerformanceBenchmarker, suite_name: str, queries: List[str]) -> None:
    """Run a suite of agent queries and benchmark their performance."""
    print(f"\n🔍 Running {suite_name}...")
    
    suite = benchmarker.create_suite(suite_name)
    
    for iteration in range(benchmarker.iterations):
        if benchmarker.iterations > 1:
            print(f"\n  Iteration {iteration + 1}/{benchmarker.iterations}:")
        
        for query in queries:
            result = await benchmark_agent_query(benchmarker, query)
            suite.add_result(result)
            benchmarker.print_result(result)
    
    benchmarker.print_suite_summary(suite)


async def benchmark_agent_query(benchmarker: PerformanceBenchmarker, query: str) -> BenchmarkResult:
    """Benchmark a single agent query using trace_agent.py."""
    start_time = time.perf_counter()
    success = True
    error = None
    metadata = {}
    
    # Determine timeout based on query complexity
    is_simple = benchmarker.is_agent_query_simple(query)
    timeout_seconds = 30 if is_simple else 60  # 30s for simple, 60s for complex queries
    metadata["query_complexity"] = "simple" if is_simple else "complex"
    metadata["timeout_seconds"] = timeout_seconds
    
    try:
        # Run trace_agent.py as a subprocess
        trace_script = benchmarker.project_root / "scripts" / "trace_agent.py"
        
        # Create a temporary file to capture output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as temp_file:
            temp_path = temp_file.name
        
        try:
            # Run the trace script with the query
            result = subprocess.run([
                sys.executable, str(trace_script),
                "--message", query,
                "--max-events", "50",  # Limit output for benchmarking
                "--pretty"
            ], 
            cwd=str(benchmarker.project_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds
            )
            
            if result.returncode == 0:
                metadata["stdout_length"] = len(result.stdout)
                metadata["stderr_length"] = len(result.stderr)
                metadata["query"] = query
                
                # Try to extract timing information from the output
                if "RESPONSE" in result.stdout:
                    metadata["has_response"] = True
                else:
                    metadata["has_response"] = False
            else:
                success = False
                error = f"Trace script failed with return code {result.returncode}: {result.stderr}"
                
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception:
                pass
                
    except subprocess.TimeoutExpired:
        success = False
        error = f"Agent query timed out after {timeout_seconds} seconds"
    except Exception as e:
        success = False
        error = str(e)
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return BenchmarkResult(
        operation=f"Agent Query: {query[:50]}{'...' if len(query) > 50 else ''}",
        service="Agent",
        duration_ms=duration_ms,
        success=success,
        error=error,
        metadata=metadata
    )


async def run_agent_performance_comparison(benchmarker: PerformanceBenchmarker, queries: List[str]) -> None:
    """Compare agent performance across different query types."""
    print("\n🔄 Running Agent Performance Comparison...")
    
    # Group queries by complexity (simple heuristic: word count and complexity indicators)
    simple_queries = []
    complex_queries = []
    
    for query in queries:
        word_count = len(query.split())
        has_filters = any(word in query.lower() for word in ['with', 'above', 'below', 'from', 'to', 'that', 'similar'])
        has_multiple_conditions = query.count('and') + query.count('but') + query.count('or') > 0
        
        if word_count <= 5 and not has_filters and not has_multiple_conditions:
            simple_queries.append(query)
        else:
            complex_queries.append(query)
    
    # Benchmark simple vs complex queries
    if simple_queries:
        simple_suite = benchmarker.create_suite("Simple Agent Queries (Comparison)")
        for query in simple_queries[:3]:  # Limit to 3 for comparison
            result = await benchmark_agent_query(benchmarker, query)
            simple_suite.add_result(result)
        benchmarker.print_suite_summary(simple_suite)
    
    if complex_queries:
        complex_suite = benchmarker.create_suite("Complex Agent Queries (Comparison)")
        for query in complex_queries[:3]:  # Limit to 3 for comparison
            result = await benchmark_agent_query(benchmarker, query)
            complex_suite.add_result(result)
        benchmarker.print_suite_summary(complex_suite)
    
    # Print comparison insights
    if simple_queries and complex_queries:
        simple_stats = benchmarker.suites.get("Simple Agent Queries (Comparison)", BenchmarkSuite("")).get_stats()
        complex_stats = benchmarker.suites.get("Complex Agent Queries (Comparison)", BenchmarkSuite("")).get_stats()
        
        if simple_stats and complex_stats:
            print(f"\n📊 Agent Query Complexity Comparison:")
            print(f"  Simple queries: {simple_stats['mean_ms']:.1f}ms average")
            print(f"  Complex queries: {complex_stats['mean_ms']:.1f}ms average")
            
            if complex_stats['mean_ms'] > simple_stats['mean_ms']:
                complexity_factor = complex_stats['mean_ms'] / simple_stats['mean_ms']
                print(f"  Complexity factor: {complexity_factor:.2f}x slower")
                
                if complexity_factor > 3.0:
                    print(f"  ⚠️  Complex queries are significantly slower - consider optimization")
                elif complexity_factor > 2.0:
                    print(f"  ⚠️  Complex queries are moderately slower")
                else:
                    print(f"  ✅ Query complexity has reasonable performance impact")


async def run_tool_integration_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run comprehensive tool integration benchmarks."""
    print("\n🔧 Running Tool Integration Benchmarks...")
    
    try:
        # Test tool registry functionality
        await run_tool_registry_benchmarks(benchmarker)
        
        # Test individual tool implementations
        await run_plex_tool_benchmarks(benchmarker, args)
        await run_tmdb_tool_benchmarks(benchmarker, args)
        await run_radarr_tool_benchmarks(benchmarker, args)
        await run_sonarr_tool_benchmarks(benchmarker, args)
        
        # Test tool result caching
        await run_tool_cache_benchmarks(benchmarker)
        
    except Exception as e:
        print(f"  ❌ Tool integration benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


async def run_tool_registry_benchmarks(benchmarker: PerformanceBenchmarker) -> None:
    """Benchmark tool registry functionality."""
    print("\n📋 Testing Tool Registry...")
    
    try:
        from bot.tools.registry_cache import get_cached_registry, initialize_registry_cache
        from llm.clients import LLMClient
        
        # Initialize LLM client for registry
        api_key = benchmarker.settings.openai_api_key or benchmarker.settings.openrouter_api_key or ""
        if not api_key:
            print("  ⚠️  Skipping tool registry tests - no LLM API key")
            return
        
        llm_client = LLMClient(api_key)
        
        # Benchmark registry building
        def build_registry_wrapper(project_root, llm_client):
            initialize_registry_cache(project_root)
            return get_cached_registry(llm_client)
        
        registry_ops = [
            ("Build Tool Registry", "Registry", build_registry_wrapper, (benchmarker.project_root, llm_client), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Tool Registry Operations", registry_ops)
        
    except Exception as e:
        print(f"  ❌ Tool registry benchmarks failed: {e}")


async def run_plex_tool_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Plex tool implementations."""
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print("  ⚠️  Skipping Plex tool benchmarks - configuration missing")
        return
    
    print("\n📋 Testing Plex Tool Implementations...")
    
    try:
        from bot.tools.tool_impl_plex import (
            make_get_plex_library_sections,
            make_get_plex_recently_added,
            make_get_plex_unwatched,
            make_get_plex_on_deck,
            make_get_plex_item_details,
        )
        
        # Create tool instances
        get_sections = make_get_plex_library_sections(benchmarker.project_root)
        get_recent = make_get_plex_recently_added(benchmarker.project_root)
        get_unwatched = make_get_plex_unwatched(benchmarker.project_root)
        get_on_deck = make_get_plex_on_deck(benchmarker.project_root)
        
        # Test tool operations
        tool_ops = [
            ("Get Library Sections Tool", "PlexTool", get_sections, ({},), {}),
            ("Get Recently Added Tool", "PlexTool", get_recent, ({"section_type": "movie", "limit": 5},), {}),
            ("Get Unwatched Tool", "PlexTool", get_unwatched, ({"section_type": "movie", "limit": 5},), {}),
            ("Get On Deck Tool", "PlexTool", get_on_deck, ({"limit": 5},), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Plex Tool Implementations", tool_ops)
        
    except Exception as e:
        print(f"  ❌ Plex tool benchmarks failed: {e}")


async def run_tmdb_tool_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark TMDb tool implementations."""
    if not benchmarker.settings.tmdb_api_key:
        print("  ⚠️  Skipping TMDb tool benchmarks - configuration missing")
        return
    
    print("\n📋 Testing TMDb Tool Implementations...")
    
    try:
        from bot.tools.tool_impl_tmdb import (
            make_tmdb_search,
            make_tmdb_popular_movies,
            make_tmdb_trending,
            make_tmdb_discover_movies,
        )
        
        # Create tool instances
        tmdb_search = make_tmdb_search(benchmarker.project_root)
        tmdb_popular = make_tmdb_popular_movies(benchmarker.project_root)
        tmdb_trending = make_tmdb_trending(benchmarker.project_root)
        tmdb_discover = make_tmdb_discover_movies(benchmarker.project_root)
        
        # Test tool operations
        tool_ops = [
            ("TMDb Search Tool", "TMDbTool", tmdb_search, ({"query": "inception"},), {}),
            ("TMDb Popular Movies Tool", "TMDbTool", tmdb_popular, ({"page": 1},), {}),
            ("TMDb Trending Tool", "TMDbTool", tmdb_trending, ({"media_type": "movie", "time_window": "week"},), {}),
            ("TMDb Discover Movies Tool", "TMDbTool", tmdb_discover, ({"sort_by": "popularity.desc"},), {}),
        ]
        
        await benchmarker.run_benchmark_suite("TMDb Tool Implementations", tool_ops)
        
    except Exception as e:
        print(f"  ❌ TMDb tool benchmarks failed: {e}")


async def run_radarr_tool_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Radarr tool implementations."""
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print("  ⚠️  Skipping Radarr tool benchmarks - configuration missing")
        return
    
    print("\n📋 Testing Radarr Tool Implementations...")
    
    try:
        from bot.tools.tool_impl_radarr import (
            make_radarr_get_movies,
            make_radarr_get_queue,
            make_radarr_system_status,
        )
        
        # Create tool instances
        get_movies = make_radarr_get_movies(benchmarker.project_root)
        get_queue = make_radarr_get_queue(benchmarker.project_root)
        get_status = make_radarr_system_status(benchmarker.project_root)
        
        # Test tool operations (read-only for benchmarking)
        tool_ops = [
            ("Radarr Get Movies Tool", "RadarrTool", get_movies, ({},), {}),
            ("Radarr Get Queue Tool", "RadarrTool", get_queue, ({},), {}),
            ("Radarr System Status Tool", "RadarrTool", get_status, ({},), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Radarr Tool Implementations", tool_ops)
        
    except Exception as e:
        print(f"  ❌ Radarr tool benchmarks failed: {e}")


async def run_sonarr_tool_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Sonarr tool implementations."""
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print("  ⚠️  Skipping Sonarr tool benchmarks - configuration missing")
        return
    
    print("\n📋 Testing Sonarr Tool Implementations...")
    
    try:
        from bot.tools.tool_impl_sonarr import (
            make_sonarr_get_series,
            make_sonarr_get_queue,
            make_sonarr_system_status,
        )
        
        # Create tool instances
        get_series = make_sonarr_get_series(benchmarker.project_root)
        get_queue = make_sonarr_get_queue(benchmarker.project_root)
        get_status = make_sonarr_system_status(benchmarker.project_root)
        
        # Test tool operations (read-only for benchmarking)
        tool_ops = [
            ("Sonarr Get Series Tool", "SonarrTool", get_series, ({},), {}),
            ("Sonarr Get Queue Tool", "SonarrTool", get_queue, ({},), {}),
            ("Sonarr System Status Tool", "SonarrTool", get_status, ({},), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Sonarr Tool Implementations", tool_ops)
        
    except Exception as e:
        print(f"  ❌ Sonarr tool benchmarks failed: {e}")


async def run_tool_cache_benchmarks(benchmarker: PerformanceBenchmarker) -> None:
    """Benchmark tool result caching functionality."""
    print("\n📋 Testing Tool Result Caching...")
    
    try:
        from bot.tools.result_cache import put_tool_result, fetch_cached_result
        
        # Test cache operations
        cache_ops = [
            ("Cache Put Operation", "Cache", put_tool_result, ({"test": "data"}, 60), {}),
            ("Cache Get Operation", "Cache", fetch_cached_result, ("test_ref_id",), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Tool Result Cache", cache_ops)
        
    except Exception as e:
        print(f"  ❌ Tool cache benchmarks failed: {e}")


async def run_worker_integration_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run comprehensive worker integration benchmarks."""
    print("\n⚙️ Running Worker Integration Benchmarks...")
    
    try:
        # Test individual workers
        await run_plex_worker_benchmarks(benchmarker, args)
        await run_tmdb_worker_benchmarks(benchmarker, args)
        await run_radarr_worker_benchmarks(benchmarker, args)
        await run_sonarr_worker_benchmarks(benchmarker, args)
        await run_summarizer_worker_benchmarks(benchmarker, args)
        
    except Exception as e:
        print(f"  ❌ Worker integration benchmarks failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()


async def run_plex_worker_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Plex worker functionality."""
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print("  ⚠️  Skipping Plex worker benchmarks - configuration missing")
        return
    
    print("\n⚙️ Testing Plex Workers...")
    
    try:
        from bot.workers.plex import PlexWorker
        from bot.workers.plex_search import PlexSearchWorker
        
        # Initialize workers
        plex_worker = PlexWorker(benchmarker.project_root)
        plex_search_worker = PlexSearchWorker(benchmarker.project_root)
        
        # Test worker operations
        async def plex_get_sections():
            return await plex_worker.get_library_sections()
        
        async def plex_get_recent():
            return await plex_worker.get_recently_added(section_type="movie", limit=5, response_level="compact")
        
        worker_ops = [
            ("Plex Worker - Get Library Sections", "PlexWorker", plex_get_sections, (), {}),
            ("Plex Worker - Get Recently Added", "PlexWorker", plex_get_recent, (), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Plex Workers", worker_ops)
        
    except Exception as e:
        print(f"  ❌ Plex worker benchmarks failed: {e}")


async def run_tmdb_worker_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark TMDb worker functionality."""
    if not benchmarker.settings.tmdb_api_key:
        print("  ⚠️  Skipping TMDb worker benchmarks - configuration missing")
        return
    
    print("\n⚙️ Testing TMDb Workers...")
    
    try:
        from bot.workers.tmdb import TMDbWorker
        
        # Initialize worker
        tmdb_worker = TMDbWorker(benchmarker.project_root)
        
        # Test worker operations
        async def tmdb_search():
            return await tmdb_worker.search_movie(query="inception")
        
        async def tmdb_popular():
            return await tmdb_worker.popular_movies(page=1)
        
        worker_ops = [
            ("TMDb Worker - Search Movies", "TMDbWorker", tmdb_search, (), {}),
            ("TMDb Worker - Get Popular Movies", "TMDbWorker", tmdb_popular, (), {}),
        ]
        
        await benchmarker.run_benchmark_suite("TMDb Workers", worker_ops)
        
    except Exception as e:
        print(f"  ❌ TMDb worker benchmarks failed: {e}")


async def run_radarr_worker_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Radarr worker functionality."""
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print("  ⚠️  Skipping Radarr worker benchmarks - configuration missing")
        return
    
    print("\n⚙️ Testing Radarr Workers...")
    
    try:
        from bot.workers.radarr import RadarrWorker
        
        # Initialize worker
        radarr_worker = RadarrWorker(benchmarker.project_root)
        
        # Test worker operations
        async def radarr_get_movies():
            return await radarr_worker.get_movies()
        
        async def radarr_get_queue():
            return await radarr_worker.get_queue()
        
        async def radarr_get_status():
            return await radarr_worker.system_status()
        
        worker_ops = [
            ("Radarr Worker - Get Movies", "RadarrWorker", radarr_get_movies, (), {}),
            ("Radarr Worker - Get Queue", "RadarrWorker", radarr_get_queue, (), {}),
            ("Radarr Worker - System Status", "RadarrWorker", radarr_get_status, (), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Radarr Workers", worker_ops)
        
    except Exception as e:
        print(f"  ❌ Radarr worker benchmarks failed: {e}")


async def run_sonarr_worker_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark Sonarr worker functionality."""
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print("  ⚠️  Skipping Sonarr worker benchmarks - configuration missing")
        return
    
    print("\n⚙️ Testing Sonarr Workers...")
    
    try:
        from bot.workers.sonarr import SonarrWorker
        
        # Initialize worker
        sonarr_worker = SonarrWorker(benchmarker.project_root)
        
        # Test worker operations
        async def sonarr_get_series():
            return await sonarr_worker.get_series()
        
        async def sonarr_get_queue():
            return await sonarr_worker.get_queue()
        
        async def sonarr_get_status():
            return await sonarr_worker.system_status()
        
        worker_ops = [
            ("Sonarr Worker - Get Series", "SonarrWorker", sonarr_get_series, (), {}),
            ("Sonarr Worker - Get Queue", "SonarrWorker", sonarr_get_queue, (), {}),
            ("Sonarr Worker - System Status", "SonarrWorker", sonarr_get_status, (), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Sonarr Workers", worker_ops)
        
    except Exception as e:
        print(f"  ❌ Sonarr worker benchmarks failed: {e}")


async def run_summarizer_worker_benchmarks(benchmarker: PerformanceBenchmarker, args) -> None:
    """Benchmark summarizer worker functionality."""
    if not benchmarker.settings.openai_api_key and not benchmarker.settings.openrouter_api_key:
        print("  ⚠️  Skipping summarizer worker benchmarks - no LLM API key")
        return
    
    print("\n⚙️ Testing Summarizer Workers...")
    
    try:
        from bot.workers.summarizer import SummarizerWorker
        
        # Initialize worker with API key
        api_key = benchmarker.settings.openai_api_key or benchmarker.settings.openrouter_api_key or ""
        if not api_key:
            print("  ⚠️  Skipping summarizer worker tests - no LLM API key")
            return
        
        summarizer_worker = SummarizerWorker(api_key)
        
        # Test worker operations
        async def summarize_test():
            try:
                result = await summarizer_worker.summarize_json(
                    benchmarker.project_root, 
                    [{"title": "Test Movie", "year": 2023}], 
                    schema_hint="movie_list", 
                    target_chars=200
                )
                return {"summary": result, "success": True}
            except Exception as e:
                return {"error": str(e), "success": False}
        
        worker_ops = [
            ("Summarizer Worker - Summarize JSON", "SummarizerWorker", summarize_test, (), {}),
        ]
        
        await benchmarker.run_benchmark_suite("Summarizer Workers", worker_ops)
        
    except Exception as e:
        print(f"  ❌ Summarizer worker benchmarks failed: {e}")


def print_final_summary(benchmarker: PerformanceBenchmarker) -> None:
    """Print comprehensive final summary of all benchmark results."""
    print("\n" + "=" * 60)
    print("📊 FINAL BENCHMARK SUMMARY")
    print("=" * 60)
    
    if not benchmarker.suites:
        print("No benchmark suites were executed.")
        return
    
    total_operations = 0
    total_successes = 0
    total_failures = 0
    slow_operations = 0
    
    for suite_name, suite in benchmarker.suites.items():
        stats = suite.get_stats()
        if stats and 'success_count' in stats:
            total_operations += stats['success_count'] + stats['failure_count']
            total_successes += stats['success_count']
            total_failures += stats['failure_count']
            
            # Use appropriate threshold based on suite type
            threshold = benchmarker.slow_threshold_ms
            if "Agent" in suite_name:
                threshold = benchmarker.agent_complex_threshold_ms
            
            if 'mean_ms' in stats and stats['mean_ms'] > threshold:
                slow_operations += 1
    
    print(f"Total Operations: {total_operations}")
    print(f"Successful: {total_successes} ({total_successes/total_operations*100:.1f}%)" if total_operations > 0 else "Successful: 0")
    print(f"Failed: {total_failures} ({total_failures/total_operations*100:.1f}%)" if total_operations > 0 else "Failed: 0")
    print(f"Slow Suites (>={benchmarker.slow_threshold_ms}ms): {slow_operations}/{len(benchmarker.suites)}")
    
    if slow_operations > 0:
        print(f"\n⚠️  WARNING: {slow_operations} benchmark suite(s) exceeded their thresholds")
        print(f"   - Standard threshold: {benchmarker.slow_threshold_ms}ms")
        print(f"   - Agent simple queries: {benchmarker.agent_simple_threshold_ms/1000:.0f}s")
        print(f"   - Agent complex queries: {benchmarker.agent_complex_threshold_ms/1000:.0f}s")
        print("   Consider investigating performance bottlenecks in these areas.")
    
    print("\nDetailed Results by Suite:")
    for suite_name, suite in benchmarker.suites.items():
        benchmarker.print_suite_summary(suite)


async def main() -> int:
    """Main entry point."""
    args = build_argparser().parse_args()
    
    # Validate arguments
    service_flags = [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
    if sum(service_flags) > 1:
        print("❌ Error: Only one service-specific flag can be used at a time")
        return 1
    
    if args.iterations < 1:
        print("❌ Error: Iterations must be at least 1")
        return 1
    
    if args.threshold < 0:
        print("❌ Error: Threshold must be non-negative")
        return 1
    
    if args.agent_simple_threshold < 0:
        print("❌ Error: Agent simple threshold must be non-negative")
        return 1
    
    if args.agent_complex_threshold < 0:
        print("❌ Error: Agent complex threshold must be non-negative")
        return 1
    
    if args.agent_simple_threshold >= args.agent_complex_threshold:
        print("❌ Error: Agent simple threshold must be less than complex threshold")
        return 1
    
    print("🎬 MovieBot Performance Benchmarking Tool")
    print("=" * 50)
    print(f"Project root: {_PROJECT_ROOT}")
    print(f"Iterations: {args.iterations}")
    print(f"Slow threshold: {args.threshold}ms")
    print(f"Agent simple threshold: {args.agent_simple_threshold}s")
    print(f"Agent complex threshold: {args.agent_complex_threshold}s")
    print(f"Verbose: {args.verbose}")
    
    # Initialize benchmarker
    benchmarker = PerformanceBenchmarker(
        project_root=_PROJECT_ROOT,
        iterations=args.iterations,
        verbose=args.verbose
    )
    benchmarker.slow_threshold_ms = args.threshold
    benchmarker.agent_simple_threshold_ms = args.agent_simple_threshold * 1000  # Convert to milliseconds
    benchmarker.agent_complex_threshold_ms = args.agent_complex_threshold * 1000  # Convert to milliseconds
    
    # Determine which services to test
    test_plex = args.plex_only or not any(service_flags)
    test_radarr = args.radarr_only or not any(service_flags)
    test_sonarr = args.sonarr_only or not any(service_flags)
    test_tmdb = args.tmdb_only or not any(service_flags)
    test_agent = args.agent_only or not any(service_flags)
    
    print(f"\nServices to test: ", end="")
    services = []
    if test_plex: services.append("Plex")
    if test_radarr: services.append("Radarr")
    if test_sonarr: services.append("Sonarr")
    if test_tmdb: services.append("TMDb")
    if test_agent: services.append("Agent")
    print(", ".join(services))
    
    try:
        # Validate environment and configuration
        print("\n🔧 Validating environment and configuration...")
        validation_result = await validate_environment(benchmarker)
        if not validation_result:
            print("❌ Environment validation failed. Please check your .env file and configuration.")
            return 1
        
        # Run service-specific benchmarks
        if test_plex and not args.skip_connectivity:
            await run_plex_benchmarks(benchmarker, args)
        
        if test_radarr and not args.skip_connectivity:
            await run_radarr_benchmarks(benchmarker, args)
        
        if test_sonarr and not args.skip_connectivity:
            await run_sonarr_benchmarks(benchmarker, args)
        
        if test_tmdb and not args.skip_connectivity:
            await run_tmdb_benchmarks(benchmarker, args)
        
        if test_agent and not args.skip_agent:
            await run_agent_benchmarks(benchmarker, args)
        
        # Run tool and worker integration tests
        if not args.skip_tools:
            await run_tool_integration_benchmarks(benchmarker, args)
        
        if not args.skip_workers:
            await run_worker_integration_benchmarks(benchmarker, args)
        
        # Print final summary
        print_final_summary(benchmarker)
        
        # Clean up resources
        await benchmarker.cleanup()
        
        print("\n✅ Benchmarking complete!")
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️ Benchmarking interrupted by user")
        await benchmarker.cleanup()
        return 1
    except Exception as e:
        print(f"\n❌ Benchmarking failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        await benchmarker.cleanup()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
