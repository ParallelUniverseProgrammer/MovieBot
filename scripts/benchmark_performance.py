#!/usr/bin/env python3
"""
MovieBot Performance Benchmarking Tool (Optimized)

This script benchmarks MovieBot integrations and operations to measure
performance, identify bottlenecks, and ensure optimal operation.

Key Improvements:
- Concurrency: Parallelize operations within suites with a global semaphore.
- Async-safe: Run sync calls in threads; async calls with timeouts.
- Non-blocking agent subprocesses via asyncio.create_subprocess_exec.
- More thorough reporting: p90/p95/p99, slow counts, per-service summary,
  top slow operations (when verbose).
- Better CLI: sane defaults, global concurrency, service-parallelism,
  JSON/CSV/JUnit outputs, warmup iterations, timeouts, no-emoji/no-color,
  fail-on-{error,slow}.
- Compatibility: Preserves existing flags, function names, and behavior
  for the rest of the project. Existing flags still work.

Features:
- Individual API call timing with metadata
- End-to-end operation timing
- Sequential vs parallel comparisons
- Agent query benchmarking via trace_agent.py
- Configurable iterations, warmup, timeouts, concurrency
- Advanced statistical analysis (mean, median, stdev, p90/p95/p99)
- Performance threshold monitoring per-suite and per-agent complexity
- Service- and suite-specific filtering options
- Optional export to JSON/CSV/JUnit
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load environment variables from .env at project root
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except Exception:
    pass

from config.loader import (
    is_config_complete,
    load_runtime_config,
    load_settings,
)


# ------------- Small styling helpers (no third-party deps) -------------


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


class Style:
    def __init__(self, color: bool, emoji: bool):
        self.color = color
        self.emoji = emoji

    def green(self, s: str) -> str:
        if not self.color:
            return s
        return f"\033[32m{s}\033[0m"

    def yellow(self, s: str) -> str:
        if not self.color:
            return s
        return f"\033[33m{s}\033[0m"

    def red(self, s: str) -> str:
        if not self.color:
            return s
        return f"\033[31m{s}\033[0m"

    def cyan(self, s: str) -> str:
        if not self.color:
            return s
        return f"\033[36m{s}\033[0m"

    def bold(self, s: str) -> str:
        if not self.color:
            return s
        return f"\033[1m{s}\033[0m"

    def ok(self) -> str:
        return "✅" if self.emoji else "[OK]"

    def warn(self) -> str:
        return "⚠️" if self.emoji else "[WARN]"

    def fail(self) -> str:
        return "❌" if self.emoji else "[FAIL]"

    def search(self) -> str:
        return "🔍" if self.emoji else "[SUITE]"

    def reload(self) -> str:
        return "🔄" if self.emoji else "[PAR]"

    def chart(self) -> str:
        return "📊" if self.emoji else "[STATS]"

    def gear(self) -> str:
        return "⚙️" if self.emoji else "[WORKERS]"

    def wrench(self) -> str:
        return "🔧" if self.emoji else "[TOOLS]"

    def film(self) -> str:
        return "🎬" if self.emoji else "[MovieBot]"


# ---------------------------- Data classes -----------------------------


@dataclass
class BenchmarkResult:
    """Individual benchmark result with timing and metadata."""
    operation: str
    service: str
    duration_ms: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_ns: Optional[int] = None
    end_ns: Optional[int] = None
    cpu_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Ensure not to explode nested objects; metadata should be JSON-serializable
        return d


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results for a specific test suite."""
    name: str
    results: List[BenchmarkResult] = field(default_factory=list)
    iterations: int = 1

    def add_result(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def _percentile(self, data: List[float], p: float) -> float:
        if not data:
            return 0.0
        if len(data) == 1:
            return data[0]
        k = (len(data) - 1) * p
        f = int(k)
        c = min(f + 1, len(data) - 1)
        if f == c:
            return data[f]
        return data[f] + (data[c] - data[f]) * (k - f)

    def get_stats(self) -> Dict[str, Any]:
        """Calculate statistics for this benchmark suite."""
        if not self.results:
            return {}
        durations = [r.duration_ms for r in self.results if r.success]
        if not durations:
            return {
                "success_count": 0,
                "failure_count": len(self.results),
            }
        durations_sorted = sorted(durations)
        return {
            "success_count": len(durations),
            "failure_count": len(self.results) - len(durations),
            "mean_ms": round(statistics.mean(durations), 2),
            "median_ms": round(statistics.median(durations), 2),
            "min_ms": round(min(durations), 2),
            "max_ms": round(max(durations), 2),
            "stdev_ms": round(
                statistics.stdev(durations) if len(durations) > 1 else 0, 2
            ),
            "p90_ms": round(self._percentile(durations_sorted, 0.9), 2),
            "p95_ms": round(self._percentile(durations_sorted, 0.95), 2),
            "p99_ms": round(self._percentile(durations_sorted, 0.99), 2),
        }


# --------------------------- Benchmarker core --------------------------


class PerformanceBenchmarker:
    """Main benchmarking orchestrator."""

    def __init__(
        self,
        project_root: Path,
        iterations: int = 3,
        verbose: bool = False,
        concurrency: int = 16,
        op_timeout_ms: int = 0,
        no_color: bool = False,
        no_emoji: bool = False,
    ):
        self.project_root = project_root
        self.iterations = iterations
        self.verbose = verbose
        self.suites: Dict[str, BenchmarkSuite] = {}
        self.settings = load_settings(project_root)
        self.config = load_runtime_config(project_root)
        self.slow_threshold_ms = 1000.0

        # Agent-specific thresholds (in milliseconds)
        self.agent_simple_threshold_ms = 30000.0  # 30s
        self.agent_complex_threshold_ms = 60000.0  # 60s

        # Concurrency and timeouts
        self.max_concurrency = max(1, concurrency)
        self._sem = asyncio.Semaphore(self.max_concurrency)
        self.op_timeout_ms = max(0, op_timeout_ms)

        # Cleanups to run at the end
        self._cleanup_tasks: List[Any] = []

        # Styling
        use_color = _supports_color() and not no_color
        self.style = Style(color=use_color, emoji=(not no_emoji))

    def create_suite(self, name: str) -> BenchmarkSuite:
        suite = BenchmarkSuite(name=name, iterations=self.iterations)
        self.suites[name] = suite
        return suite

    def is_agent_query_simple(self, query: str) -> bool:
        wc = len(query.split())
        text = query.lower()
        has_filters = any(
            w in text
            for w in ["with", "above", "below", "from", "to", "that", "similar"]
        )
        has_multi = text.count(" and ") + text.count(" but ") + text.count(" or ") > 0
        return wc <= 5 and not has_filters and not has_multi

    def get_agent_threshold(self, query: str) -> float:
        if self.is_agent_query_simple(query):
            return self.agent_simple_threshold_ms
        return self.agent_complex_threshold_ms

    async def time_operation(
        self,
        operation_name: str,
        service: str,
        func,
        *args,
        **kwargs,
    ) -> BenchmarkResult:
        """Time a single operation, honoring global concurrency and timeouts.

        - Async call: awaited under timeout (if configured).
        - Sync call: executed in a thread via asyncio.to_thread.
        """
        start_ns = time.perf_counter_ns()
        start_cpu = time.process_time()
        success = True
        error = None
        metadata: Dict[str, Any] = {}

        async def _run_call():
            if asyncio.iscoroutinefunction(func):
                if self.op_timeout_ms > 0:
                    return await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=self.op_timeout_ms / 1000.0,
                    )
                return await func(*args, **kwargs)
            else:
                # Run sync function in thread; honor timeout by wrapping
                coro = asyncio.to_thread(func, *args, **kwargs)
                if self.op_timeout_ms > 0:
                    return await asyncio.wait_for(
                        coro, timeout=self.op_timeout_ms / 1000.0
                    )
                return await coro

        async with self._sem:
            try:
                result = await _run_call()
                metadata["result_type"] = type(result).__name__
                if isinstance(result, dict):
                    metadata["result_keys"] = list(result.keys())
                elif isinstance(result, (list, tuple, set)):
                    metadata["result_len"] = len(result)  # non-breaking
            except asyncio.TimeoutError:
                success = False
                error = (
                    f"Operation timed out after "
                    f"{self.op_timeout_ms/1000.0:.1f}s"
                    if self.op_timeout_ms > 0
                    else "Operation timed out"
                )
                result = None
            except Exception as e:
                success = False
                error = str(e)
                result = None

        end_ns = time.perf_counter_ns()
        end_cpu = time.process_time()
        duration_ms = (end_ns - start_ns) / 1_000_000.0
        cpu_ms = (end_cpu - start_cpu) * 1000.0

        return BenchmarkResult(
            operation=operation_name,
            service=service,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=metadata,
            start_ns=start_ns,
            end_ns=end_ns,
            cpu_ms=cpu_ms,
        )

    def print_result(self, result: BenchmarkResult) -> None:
        """Print a single benchmark result."""
        s = self.style
        status = s.ok() if result.success else s.fail()
        duration_str = f"{result.duration_ms:.1f}ms"

        # Determine threshold based on service and query complexity
        threshold = self.slow_threshold_ms
        if result.service == "Agent" and "query" in result.metadata:
            threshold = self.get_agent_threshold(result.metadata["query"])

        # Add warning for slow operations
        slow_note = ""
        if result.success and result.duration_ms > threshold:
            slow_note = f" {s.warn()} SLOW"
            if result.service == "Agent":
                q = result.metadata.get("query", "")
                complexity = (
                    "simple" if self.is_agent_query_simple(q) else "complex"
                )
                slow_note += f" (>{complexity} threshold)"

        if result.success:
            msg = (
                f"  {status} {result.operation} [{result.service}]: "
                f"{s.green(duration_str)}{slow_note}"
            )
        else:
            msg = (
                f"  {status} {result.operation} [{result.service}]: "
                f"{s.red(duration_str)}"
            )

        print(msg)
        if not result.success and self.verbose and result.error:
            print(f"    Error: {s.red(result.error)}")
        if self.verbose and result.metadata:
            # Avoid overly noisy dumps
            meta = {
                k: v
                for k, v in result.metadata.items()
                if k not in {"stdout", "stderr"}
            }
            print(f"    Metadata: {meta}")

    def print_suite_summary(self, suite: BenchmarkSuite) -> None:
        """Print summary statistics for a benchmark suite."""
        s = self.style
        stats = suite.get_stats()
        if not stats:
            print(f"\n{self.style.chart()} {suite.name}: No results")
            return

        total = stats["success_count"] + stats["failure_count"]
        print(f"\n{s.chart()} {s.bold(suite.name)} Summary:")
        print(f"  Success: {stats['success_count']}/{total}")
        if stats["success_count"] > 0:
            timing = (
                f"{stats['mean_ms']:.1f}ms avg, "
                f"{stats['min_ms']:.1f}-{stats['max_ms']:.1f}ms range, "
                f"p90 {stats['p90_ms']:.1f}ms, "
                f"p95 {stats['p95_ms']:.1f}ms, "
                f"p99 {stats['p99_ms']:.1f}ms"
            )
            print(f"  Timing: {timing}")
            if stats["stdev_ms"] > 0:
                print(f"  Variability: ±{stats['stdev_ms']:.1f}ms stdev")

            # Determine appropriate threshold for this suite
            threshold = self.slow_threshold_ms
            if "Agent" in suite.name:
                threshold = self.agent_complex_threshold_ms
            if stats["mean_ms"] > threshold:
                if "Agent" in suite.name:
                    print(
                        f"  {s.warn()} WARNING: Average exceeds "
                        f"{threshold/1000:.0f}s agent threshold"
                    )
                else:
                    print(
                        f"  {s.warn()} WARNING: Average exceeds "
                        f"{threshold:.0f}ms threshold"
                    )

        if self.verbose:
            # Print top 3 slowest successful ops in this suite
            slow_results = sorted(
                [r for r in suite.results if r.success],
                key=lambda r: r.duration_ms,
                reverse=True,
            )[:3]
            if slow_results:
                print("  Slowest operations:")
                for r in slow_results:
                    print(
                        f"    - {r.operation} [{r.service}] "
                        f"took {r.duration_ms:.1f}ms"
                    )

    async def run_benchmark_suite(
        self,
        suite_name: str,
        operations: List[Tuple[str, str, callable, tuple, dict]],
        *,
        parallel: bool = True,
        warmup: int = 0,
    ) -> None:
        """Run a suite of benchmark operations.

        - parallel=True: run operations in each iteration concurrently.
        - warmup: number of warmup iterations (not recorded/printed).
        """
        s = self.style
        suite = self.create_suite(suite_name)
        print(f"\n{s.search()} Running {suite_name} benchmarks...")

        # Warmup iterations (not recorded)
        for w in range(max(0, warmup)):
            if self.iterations > 0:
                if self.verbose:
                    print(f"  Warmup {w + 1}/{warmup} ...")
                await self._run_suite_iteration(
                    operations, suite=None, record=False, parallel=parallel
                )

        # Measured iterations
        for iteration in range(self.iterations):
            if self.iterations > 1:
                print(f"\n  Iteration {iteration + 1}/{self.iterations}:")
            await self._run_suite_iteration(
                operations,
                suite=suite,
                record=True,
                parallel=parallel,
                iteration=iteration + 1,
            )

        self.print_suite_summary(suite)

    async def _run_suite_iteration(
        self,
        operations: List[Tuple[str, str, callable, tuple, dict]],
        *,
        suite: Optional[BenchmarkSuite],
        record: bool,
        parallel: bool,
        iteration: Optional[int] = None,
    ) -> None:
        """Run one iteration of a suite."""
        if parallel:
            tasks = [
                self.time_operation(op_name, service, func, *args, **kwargs)
                for (op_name, service, func, args, kwargs) in operations
            ]
            results = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            for idx, res in enumerate(results):
                if isinstance(res, BenchmarkResult):
                    if iteration is not None:
                        res.metadata["iteration"] = iteration
                    if record and suite is not None:
                        suite.add_result(res)
                    self.print_result(res)
                else:
                    # Exception bubbled out
                    op_name, service, *_ = operations[idx]
                    br = BenchmarkResult(
                        operation=op_name,
                        service=service,
                        duration_ms=0.0,
                        success=False,
                        error=str(res),
                        metadata={"iteration": iteration} if iteration else {},
                    )
                    if record and suite is not None:
                        suite.add_result(br)
                    self.print_result(br)
        else:
            # Strictly sequential when dependencies exist
            for (op_name, service, func, args, kwargs) in operations:
                res = await self.time_operation(
                    op_name, service, func, *args, **kwargs
                )
                if iteration is not None:
                    res.metadata["iteration"] = iteration
                if record and suite is not None:
                    suite.add_result(res)
                self.print_result(res)

    async def cleanup(self) -> None:
        """Clean up any resources used during benchmarking."""
        for task in self._cleanup_tasks:
            try:
                if hasattr(task, "close"):
                    await task.close()
            except Exception:
                pass
        self._cleanup_tasks.clear()


# --------------------------- CLI and helpers ---------------------------


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
  python scripts/benchmark_performance.py --agent-only \
    --agent-simple-threshold 45 --agent-complex-threshold 90

  # Run specific service benchmarks
  python scripts/benchmark_performance.py --radarr-only --sonarr-only

  # Increase concurrency and parallelize services
  python scripts/benchmark_performance.py --concurrency 24 --parallel-services

  # Emit JSON and JUnit reports
  python scripts/benchmark_performance.py --output-json out.json \
    --junit out-junit.xml
        """,
    )

    # Service selection (preserved)
    parser.add_argument(
        "--plex-only", action="store_true", help="Run only Plex benchmarks"
    )
    parser.add_argument(
        "--radarr-only", action="store_true", help="Run only Radarr benchmarks"
    )
    parser.add_argument(
        "--sonarr-only", action="store_true", help="Run only Sonarr benchmarks"
    )
    parser.add_argument(
        "--tmdb-only", action="store_true", help="Run only TMDb benchmarks"
    )
    parser.add_argument(
        "--agent-only", action="store_true", help="Run only agent benchmarks"
    )

    # Benchmark configuration (enhanced)
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Measured iterations per test (default: 3)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="Warmup iterations (not recorded; default: 0)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=16,
        help="Max concurrent operations (default: 16)",
    )
    parser.add_argument(
        "--parallel-services",
        action="store_true",
        help="Run services in parallel when possible",
    )
    parser.add_argument(
        "--op-timeout",
        type=float,
        default=0.0,
        help="Per-operation timeout in seconds (0=unlimited)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1000.0,
        help="Slow operation threshold in ms (default: 1000)",
    )
    parser.add_argument(
        "--agent-simple-threshold",
        type=float,
        default=30.0,
        help="Agent simple query threshold in seconds (default: 30)",
    )
    parser.add_argument(
        "--agent-complex-threshold",
        type=float,
        default=60.0,
        help="Agent complex query threshold in seconds (default: 60)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output with detailed metadata",
    )

    # Test selection (preserved)
    parser.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Skip basic connectivity tests",
    )
    parser.add_argument(
        "--skip-search", action="store_true", help="Skip search operation tests"
    )
    parser.add_argument(
        "--skip-metadata",
        action="store_true",
        help="Skip metadata retrieval tests",
    )
    parser.add_argument(
        "--skip-agent", action="store_true", help="Skip agent integration tests"
    )
    parser.add_argument(
        "--skip-tools", action="store_true", help="Skip tool implementation tests"
    )
    parser.add_argument(
        "--skip-workers",
        action="store_true",
        help="Skip worker integration tests",
    )

    # Reporting
    parser.add_argument(
        "--output-json", type=str, help="Write full results to JSON file"
    )
    parser.add_argument(
        "--output-csv", type=str, help="Write flat results to CSV file"
    )
    parser.add_argument(
        "--junit", type=str, help="Write JUnit XML to file (suite summary)"
    )
    parser.add_argument(
        "--no-emoji", action="store_true", help="Disable emoji in output"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable ANSI colors"
    )

    # Exit behavior
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit non-zero if any operation fails",
    )
    parser.add_argument(
        "--fail-on-slow",
        action="store_true",
        help="Exit non-zero if any suite avg exceeds threshold",
    )

    return parser


# ------------------------ Environment validation -----------------------


async def validate_environment(benchmarker: PerformanceBenchmarker) -> bool:
    """Validate that the environment is properly configured."""
    s = benchmarker.style
    print("  Checking configuration completeness...")

    if not is_config_complete(benchmarker.settings, benchmarker.config):
        print(f"  {s.fail()} Configuration incomplete - missing settings")
        return False

    required_keys = []
    # Need at least one LLM provider for agent/summarizer tools
    if (
        not benchmarker.settings.openai_api_key
        and not benchmarker.settings.openrouter_api_key
    ):
        required_keys.append("OPENAI_API_KEY or OPENROUTER_API_KEY")

    if benchmarker.settings.plex_base_url and benchmarker.settings.plex_token:
        print(f"  {s.ok()} Plex configuration found")
    else:
        print(f"  {s.warn()} Plex configuration missing (will skip Plex tests)")

    if benchmarker.settings.radarr_base_url and benchmarker.settings.radarr_api_key:
        print(f"  {s.ok()} Radarr configuration found")
    else:
        print(f"  {s.warn()} Radarr configuration missing (will skip Radarr tests)")

    if benchmarker.settings.sonarr_base_url and benchmarker.settings.sonarr_api_key:
        print(f"  {s.ok()} Sonarr configuration found")
    else:
        print(f"  {s.warn()} Sonarr configuration missing (will skip Sonarr tests)")

    if benchmarker.settings.tmdb_api_key:
        print(f"  {s.ok()} TMDb configuration found")
    else:
        print(f"  {s.warn()} TMDb configuration missing (will skip TMDb tests)")

    if required_keys:
        print(f"  {s.fail()} Missing required keys: {', '.join(required_keys)}")
        return False

    print(f"  {s.ok()} Environment validation passed")
    return True


# --------------------------- Plex benchmarks ---------------------------


async def run_plex_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    """Run Plex-specific benchmarks."""
    s = benchmarker.style
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print(f"  {s.warn()} Skipping Plex benchmarks - configuration missing")
        return

    from integrations.plex_client import PlexClient, ResponseLevel

    plex_client = PlexClient(
        benchmarker.settings.plex_base_url,
        benchmarker.settings.plex_token,
        default_response_level=ResponseLevel.COMPACT,
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
            await benchmarker.run_benchmark_suite(
                "Plex Connectivity",
                connectivity_ops,
                parallel=True,
                warmup=args.warmup,
            )

        # Search operations
        if not args.skip_search:
            search_ops = [
                (
                    "Search Movies - 'inception'",
                    "Plex",
                    plex_client.search_movies,
                    ("inception",),
                    {"response_level": ResponseLevel.COMPACT},
                ),
                (
                    "Search Shows - 'office'",
                    "Plex",
                    plex_client.search_shows,
                    ("office",),
                    {"response_level": ResponseLevel.COMPACT},
                ),
                (
                    "Search All - 'matrix'",
                    "Plex",
                    plex_client.search_all,
                    ("matrix",),
                    {"response_level": ResponseLevel.COMPACT},
                ),
                (
                    "Search Movies - 'pirates'",
                    "Plex",
                    plex_client.search_movies,
                    ("pirates",),
                    {"response_level": ResponseLevel.STANDARD},
                ),
            ]
            await benchmarker.run_benchmark_suite(
                "Plex Search Operations",
                search_ops,
                parallel=True,
                warmup=args.warmup,
            )

        # Metadata retrieval operations
        if not args.skip_metadata:
            try:
                movies = plex_client.search_movies(
                    "inception", response_level=ResponseLevel.COMPACT
                )
                shows = plex_client.search_shows(
                    "office", response_level=ResponseLevel.COMPACT
                )

                metadata_ops: List[
                    Tuple[str, str, callable, tuple, dict]
                ] = []

                if movies and len(movies) > 0:
                    first_movie = movies[0]
                    if hasattr(first_movie, "ratingKey"):
                        metadata_ops.append(
                            (
                                "Movie Details",
                                "Plex",
                                plex_client.get_item_details,
                                (first_movie.ratingKey,),
                                {"response_level": ResponseLevel.DETAILED},
                            )
                        )

                if shows and len(shows) > 0:
                    first_show = shows[0]
                    if hasattr(first_show, "ratingKey"):
                        metadata_ops.append(
                            (
                                "Show Details",
                                "Plex",
                                plex_client.get_item_details,
                                (first_show.ratingKey,),
                                {"response_level": ResponseLevel.DETAILED},
                            )
                        )

                metadata_ops.extend(
                    [
                        (
                            "Recently Added Movies",
                            "Plex",
                            plex_client.get_recently_added,
                            ("movie",),
                            {
                                "limit": 10,
                                "response_level": ResponseLevel.COMPACT,
                            },
                        ),
                        (
                            "Recently Added Shows",
                            "Plex",
                            plex_client.get_recently_added,
                            ("show",),
                            {
                                "limit": 10,
                                "response_level": ResponseLevel.COMPACT,
                            },
                        ),
                        (
                            "On Deck Items",
                            "Plex",
                            plex_client.get_on_deck,
                            (),
                            {"limit": 10, "response_level": ResponseLevel.COMPACT},
                        ),
                    ]
                )

                if metadata_ops:
                    await benchmarker.run_benchmark_suite(
                        "Plex Metadata Operations",
                        metadata_ops,
                        parallel=True,
                        warmup=args.warmup,
                    )
                else:
                    print(
                        f"  {s.warn()} Skipping metadata operations - "
                        "no items found"
                    )

            except Exception as e:
                print(
                    f"  {s.warn()} Skipping metadata operations - "
                    f"error getting test items: {e}"
                )

        # Sequential vs Parallel comparison
        if not args.skip_connectivity and not args.skip_search:
            await run_plex_parallel_comparison(benchmarker, plex_client)

    except Exception as e:
        print(f"  {s.fail()} Plex benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
    finally:
        try:
            await plex_client.close()
        except Exception:
            pass


async def run_plex_parallel_comparison(
    benchmarker: PerformanceBenchmarker, plex_client
) -> None:
    """Compare sequential vs parallel Plex operations."""
    from integrations.plex_client import ResponseLevel

    s = benchmarker.style
    print(f"\n{s.reload()} Running Plex Sequential vs Parallel Comparison...")

    operations = [
        (
            "Search Movies 1",
            plex_client.search_movies,
            ("inception",),
            {"response_level": ResponseLevel.COMPACT},
        ),
        (
            "Search Movies 2",
            plex_client.search_movies,
            ("matrix",),
            {"response_level": ResponseLevel.COMPACT},
        ),
        (
            "Search Shows 1",
            plex_client.search_shows,
            ("office",),
            {"response_level": ResponseLevel.COMPACT},
        ),
        (
            "Search Shows 2",
            plex_client.search_shows,
            ("breaking",),
            {"response_level": ResponseLevel.COMPACT},
        ),
    ]

    # Sequential
    suite_seq = benchmarker.create_suite("Plex Sequential Operations")
    start = time.perf_counter()
    for op_name, func, args, kwargs in operations:
        r = await benchmarker.time_operation(op_name, "Plex", func, *args, **kwargs)
        suite_seq.add_result(r)
        benchmarker.print_result(r)
    sequential_time = (time.perf_counter() - start) * 1000.0

    # Parallel
    suite_par = benchmarker.create_suite("Plex Parallel Operations")
    start = time.perf_counter()

    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "Plex", func, *args, **kwargs)

    tasks = [
        run_operation(op_name, func, args, kwargs)
        for (op_name, func, args, kwargs) in operations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = (time.perf_counter() - start) * 1000.0

    for res in results:
        if isinstance(res, BenchmarkResult):
            suite_par.add_result(res)
            benchmarker.print_result(res)
        else:
            print(f"  {s.fail()} Parallel operation failed: {res}")

    print(f"\n{s.chart()} Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time:   {parallel_time:.1f}ms")
    if parallel_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  {s.ok()} Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  {s.warn()} Parallel execution shows modest improvement")
        else:
            print(f"  {s.warn()} Parallel execution shows minimal improvement")

    benchmarker.print_suite_summary(suite_par)


# -------------------------- Radarr benchmarks --------------------------


async def run_radarr_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    """Run Radarr-specific benchmarks."""
    s = benchmarker.style
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print(f"  {s.warn()} Skipping Radarr benchmarks - configuration missing")
        return

    from integrations.radarr_client import RadarrClient

    radarr_client = RadarrClient(
        benchmarker.settings.radarr_base_url,
        benchmarker.settings.radarr_api_key,
    )

    try:
        if not args.skip_connectivity:
            connectivity_ops = [
                ("System Status", "Radarr", radarr_client.system_status, (), {}),
                ("Quality Profiles", "Radarr", radarr_client.quality_profiles, (), {}),
                ("Root Folders", "Radarr", radarr_client.root_folders, (), {}),
            ]
            await benchmarker.run_benchmark_suite(
                "Radarr Connectivity",
                connectivity_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_search:
            search_ops = [
                ("Get All Movies", "Radarr", radarr_client.get_movies, (), {}),
                ("Get Movie Queue", "Radarr", radarr_client.get_queue, (), {}),
                ("Get Movie History", "Radarr", radarr_client.get_history, (), {"page_size": 10}),
                ("Get Wanted Missing", "Radarr", radarr_client.get_wanted, (), {"page_size": 10}),
            ]
            await benchmarker.run_benchmark_suite(
                "Radarr Movie Operations",
                search_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_metadata:
            metadata_ops = [
                ("Get Indexers", "Radarr", radarr_client.get_indexers, (), {}),
                ("Get Download Clients", "Radarr", radarr_client.get_download_clients, (), {}),
                ("Get Notifications", "Radarr", radarr_client.get_notifications, (), {}),
                ("Get Tags", "Radarr", radarr_client.get_tags, (), {}),
            ]
            await benchmarker.run_benchmark_suite(
                "Radarr Configuration",
                metadata_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_connectivity and not args.skip_search:
            await run_radarr_parallel_comparison(benchmarker, radarr_client)

    except Exception as e:
        print(f"  {s.fail()} Radarr benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
    finally:
        try:
            await radarr_client.close()
        except Exception:
            pass


async def run_radarr_parallel_comparison(
    benchmarker: PerformanceBenchmarker, radarr_client
) -> None:
    s = benchmarker.style
    print(f"\n{s.reload()} Running Radarr Sequential vs Parallel Comparison...")

    operations = [
        ("System Status", radarr_client.system_status, (), {}),
        ("Quality Profiles", radarr_client.quality_profiles, (), {}),
        ("Root Folders", radarr_client.root_folders, (), {}),
        ("Get Movies", radarr_client.get_movies, (), {}),
    ]

    suite_seq = benchmarker.create_suite("Radarr Sequential Operations")
    start = time.perf_counter()
    for op_name, func, args, kwargs in operations:
        r = await benchmarker.time_operation(op_name, "Radarr", func, *args, **kwargs)
        suite_seq.add_result(r)
        benchmarker.print_result(r)
    sequential_time = (time.perf_counter() - start) * 1000.0

    suite_par = benchmarker.create_suite("Radarr Parallel Operations")
    start = time.perf_counter()

    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(
            op_name, "Radarr", func, *args, **kwargs
        )

    tasks = [
        run_operation(op_name, func, args, kwargs)
        for (op_name, func, args, kwargs) in operations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = (time.perf_counter() - start) * 1000.0

    for res in results:
        if isinstance(res, BenchmarkResult):
            suite_par.add_result(res)
            benchmarker.print_result(res)
        else:
            print(f"  {s.fail()} Parallel operation failed: {res}")

    print(f"\n{s.chart()} Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time:   {parallel_time:.1f}ms")
    if parallel_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  {s.ok()} Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  {s.warn()} Parallel execution shows modest improvement")
        else:
            print(f"  {s.warn()} Parallel execution shows minimal improvement")

    benchmarker.print_suite_summary(suite_par)


# -------------------------- Sonarr benchmarks --------------------------


async def run_sonarr_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    """Run Sonarr-specific benchmarks."""
    s = benchmarker.style
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print(f"  {s.warn()} Skipping Sonarr benchmarks - configuration missing")
        return

    from integrations.sonarr_client import SonarrClient

    sonarr_client = SonarrClient(
        benchmarker.settings.sonarr_base_url,
        benchmarker.settings.sonarr_api_key,
    )

    try:
        if not args.skip_connectivity:
            connectivity_ops = [
                ("System Status", "Sonarr", sonarr_client.system_status, (), {}),
                ("Quality Profiles", "Sonarr", sonarr_client.quality_profiles, (), {}),
                ("Root Folders", "Sonarr", sonarr_client.root_folders, (), {}),
            ]
            await benchmarker.run_benchmark_suite(
                "Sonarr Connectivity",
                connectivity_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_search:
            search_ops = [
                ("Get All Series", "Sonarr", sonarr_client.get_series, (), {}),
                ("Get Episode Queue", "Sonarr", sonarr_client.get_queue, (), {}),
                ("Get Episode History", "Sonarr", sonarr_client.get_history, (), {"page_size": 10}),
                ("Get Wanted Missing", "Sonarr", sonarr_client.get_wanted, (), {"page_size": 10}),
            ]
            await benchmarker.run_benchmark_suite(
                "Sonarr Series Operations",
                search_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_metadata:
            metadata_ops = [
                ("Get Import Lists", "Sonarr", sonarr_client.get_import_lists, (), {}),
                ("Get Notifications", "Sonarr", sonarr_client.get_notifications, (), {}),
                ("Get Tags", "Sonarr", sonarr_client.get_tags, (), {}),
                ("Get Calendar", "Sonarr", sonarr_client.get_calendar, (), {}),
            ]
            await benchmarker.run_benchmark_suite(
                "Sonarr Configuration",
                metadata_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_connectivity and not args.skip_search:
            await run_sonarr_parallel_comparison(benchmarker, sonarr_client)

    except Exception as e:
        print(f"  {s.fail()} Sonarr benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
    finally:
        try:
            await sonarr_client.close()
        except Exception:
            pass


async def run_sonarr_parallel_comparison(
    benchmarker: PerformanceBenchmarker, sonarr_client
) -> None:
    s = benchmarker.style
    print(f"\n{s.reload()} Running Sonarr Sequential vs Parallel Comparison...")

    operations = [
        ("System Status", sonarr_client.system_status, (), {}),
        ("Quality Profiles", sonarr_client.quality_profiles, (), {}),
        ("Root Folders", sonarr_client.root_folders, (), {}),
        ("Get Series", sonarr_client.get_series, (), {}),
    ]

    suite_seq = benchmarker.create_suite("Sonarr Sequential Operations")
    start = time.perf_counter()
    for op_name, func, args, kwargs in operations:
        r = await benchmarker.time_operation(op_name, "Sonarr", func, *args, **kwargs)
        suite_seq.add_result(r)
        benchmarker.print_result(r)
    sequential_time = (time.perf_counter() - start) * 1000.0

    suite_par = benchmarker.create_suite("Sonarr Parallel Operations")
    start = time.perf_counter()

    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(
            op_name, "Sonarr", func, *args, **kwargs
        )

    tasks = [
        run_operation(op_name, func, args, kwargs)
        for (op_name, func, args, kwargs) in operations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = (time.perf_counter() - start) * 1000.0

    for res in results:
        if isinstance(res, BenchmarkResult):
            suite_par.add_result(res)
            benchmarker.print_result(res)
        else:
            print(f"  {s.fail()} Parallel operation failed: {res}")

    print(f"\n{s.chart()} Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time:   {parallel_time:.1f}ms")
    if parallel_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  {s.ok()} Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  {s.warn()} Parallel execution shows modest improvement")
        else:
            print(f"  {s.warn()} Parallel execution shows minimal improvement")

    benchmarker.print_suite_summary(suite_par)


# --------------------------- TMDb benchmarks ---------------------------


async def run_tmdb_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    """Run TMDb-specific benchmarks."""
    s = benchmarker.style
    if not benchmarker.settings.tmdb_api_key:
        print(f"  {s.warn()} Skipping TMDb benchmarks - configuration missing")
        return

    from integrations.tmdb_client import TMDbClient, TMDbResponseLevel

    tmdb_client = TMDbClient(benchmarker.settings.tmdb_api_key)

    try:
        if not args.skip_search:
            search_ops = [
                (
                    "Search Movies - 'inception'",
                    "TMDb",
                    tmdb_client.search_movie,
                    ("inception",),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
                (
                    "Search Movies - 'matrix'",
                    "TMDb",
                    tmdb_client.search_movie,
                    ("matrix",),
                    {"response_level": TMDbResponseLevel.STANDARD},
                ),
                (
                    "Search TV Shows - 'office'",
                    "TMDb",
                    tmdb_client.search_tv,
                    ("office",),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
                (
                    "Search People - 'tom hanks'",
                    "TMDb",
                    tmdb_client.search_person,
                    ("tom hanks",),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
            ]
            await benchmarker.run_benchmark_suite(
                "TMDb Search Operations",
                search_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_metadata:
            discovery_ops = [
                (
                    "Popular Movies",
                    "TMDb",
                    tmdb_client.popular_movies,
                    (),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
                (
                    "Top Rated Movies",
                    "TMDb",
                    tmdb_client.top_rated_movies,
                    (),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
                (
                    "Now Playing Movies",
                    "TMDb",
                    tmdb_client.now_playing_movies,
                    (),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
                (
                    "Popular TV Shows",
                    "TMDb",
                    tmdb_client.popular_tv,
                    (),
                    {"response_level": TMDbResponseLevel.COMPACT},
                ),
            ]
            await benchmarker.run_benchmark_suite(
                "TMDb Discovery Operations",
                discovery_ops,
                parallel=True,
                warmup=args.warmup,
            )

        if not args.skip_search and not args.skip_metadata:
            await run_tmdb_parallel_comparison(benchmarker, tmdb_client)

    except Exception as e:
        print(f"  {s.fail()} TMDb benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
    finally:
        try:
            await tmdb_client.close()
        except Exception:
            pass


async def run_tmdb_parallel_comparison(
    benchmarker: PerformanceBenchmarker, tmdb_client
) -> None:
    from integrations.tmdb_client import TMDbResponseLevel

    s = benchmarker.style
    print(f"\n{s.reload()} Running TMDb Sequential vs Parallel Comparison...")

    operations = [
        (
            "Search Movies 1",
            tmdb_client.search_movie,
            ("inception",),
            {"response_level": TMDbResponseLevel.COMPACT},
        ),
        (
            "Search Movies 2",
            tmdb_client.search_movie,
            ("matrix",),
            {"response_level": TMDbResponseLevel.COMPACT},
        ),
        (
            "Popular Movies",
            tmdb_client.popular_movies,
            (),
            {"response_level": TMDbResponseLevel.COMPACT},
        ),
        (
            "Top Rated Movies",
            tmdb_client.top_rated_movies,
            (),
            {"response_level": TMDbResponseLevel.COMPACT},
        ),
    ]

    suite_seq = benchmarker.create_suite("TMDb Sequential Operations")
    start = time.perf_counter()
    for op_name, func, args, kwargs in operations:
        r = await benchmarker.time_operation(op_name, "TMDb", func, *args, **kwargs)
        suite_seq.add_result(r)
        benchmarker.print_result(r)
    sequential_time = (time.perf_counter() - start) * 1000.0

    suite_par = benchmarker.create_suite("TMDb Parallel Operations")
    start = time.perf_counter()

    async def run_operation(op_name, func, args, kwargs):
        return await benchmarker.time_operation(op_name, "TMDb", func, *args, **kwargs)

    tasks = [
        run_operation(op_name, func, args, kwargs)
        for (op_name, func, args, kwargs) in operations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = (time.perf_counter() - start) * 1000.0

    for res in results:
        if isinstance(res, BenchmarkResult):
            suite_par.add_result(res)
            benchmarker.print_result(res)
        else:
            print(f"  {s.fail()} Parallel operation failed: {res}")

    print(f"\n{s.chart()} Sequential vs Parallel Comparison:")
    print(f"  Sequential total time: {sequential_time:.1f}ms")
    print(f"  Parallel total time:   {parallel_time:.1f}ms")
    if parallel_time > 0:
        speedup = sequential_time / parallel_time
        print(f"  Speedup factor: {speedup:.2f}x")
        if speedup > 1.5:
            print(f"  {s.ok()} Parallel execution shows significant improvement")
        elif speedup > 1.1:
            print(f"  {s.warn()} Parallel execution shows modest improvement")
        else:
            print(f"  {s.warn()} Parallel execution shows minimal improvement")

    benchmarker.print_suite_summary(suite_par)


# --------------------------- Agent benchmarks --------------------------


async def run_agent_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    """Run agent integration benchmarks using trace_agent.py."""
    s = benchmarker.style
    if (
        not benchmarker.settings.openai_api_key
        and not benchmarker.settings.openrouter_api_key
    ):
        print(f"  {s.warn()} Skipping agent benchmarks - no LLM API key")
        return

    print(f"  🤖 Running agent integration benchmarks...")

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
        if not args.skip_search:
            await run_agent_query_suite(
                benchmarker, "Simple Agent Queries", simple_queries, warmup=args.warmup
            )

        if not args.skip_metadata:
            await run_agent_query_suite(
                benchmarker,
                "Complex Agent Queries",
                complex_queries,
                warmup=args.warmup,
            )

        if not args.skip_search and not args.skip_metadata:
            await run_agent_performance_comparison(
                benchmarker, simple_queries + complex_queries
            )

    except Exception as e:
        print(f"  {s.fail()} Agent benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()


async def run_agent_query_suite(
    benchmarker: PerformanceBenchmarker,
    suite_name: str,
    queries: List[str],
    warmup: int = 0,
) -> None:
    """Run a suite of agent queries and benchmark their performance."""
    s = benchmarker.style
    print(f"\n{s.search()} Running {suite_name}...")
    suite = benchmarker.create_suite(suite_name)

    # Warmup
    for w in range(max(0, warmup)):
        if benchmarker.iterations > 0 and benchmarker.verbose:
            print(f"  Warmup {w + 1}/{warmup} ...")
        await asyncio.gather(
            *[benchmark_agent_query(benchmarker, q, record=False) for q in queries]
        )

    for iteration in range(benchmarker.iterations):
        if benchmarker.iterations > 1:
            print(f"\n  Iteration {iteration + 1}/{benchmarker.iterations}:")
        tasks = [
            benchmark_agent_query(benchmarker, query, record=True, iteration=iteration + 1)
            for query in queries
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            suite.add_result(result)
            benchmarker.print_result(result)

    benchmarker.print_suite_summary(suite)


async def benchmark_agent_query(
    benchmarker: PerformanceBenchmarker,
    query: str,
    record: bool = True,
    iteration: Optional[int] = None,
) -> BenchmarkResult:
    """Benchmark a single agent query using trace_agent.py non-blocking."""
    start_time = time.perf_counter()
    start_ns = time.perf_counter_ns()
    start_cpu = time.process_time()
    success = True
    error = None
    metadata: Dict[str, Any] = {}

    is_simple = benchmarker.is_agent_query_simple(query)
    timeout_seconds = 30 if is_simple else 60
    metadata["query_complexity"] = "simple" if is_simple else "complex"
    metadata["timeout_seconds"] = timeout_seconds
    metadata["query"] = query
    if iteration is not None:
        metadata["iteration"] = iteration

    try:
        trace_script = benchmarker.project_root / "scripts" / "trace_agent.py"

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(trace_script),
            "--message",
            query,
            "--max-events",
            "50",
            "--pretty",
            cwd=str(benchmarker.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            success = False
            error = f"Agent query timed out after {timeout_seconds} seconds"
            stdout, stderr = b"", b""

        rc = proc.returncode if proc.returncode is not None else -1
        if success:
            metadata["stdout_length"] = len(stdout)
            metadata["stderr_length"] = len(stderr)
            metadata["has_response"] = b"RESPONSE" in stdout
            if rc != 0:
                success = False
                error = (
                    f"Trace script failed with return code {rc}: "
                    f"{stderr.decode('utf-8', errors='ignore')[:500]}"
                )

    except Exception as e:
        success = False
        error = str(e)

    end_ns = time.perf_counter_ns()
    end_cpu = time.process_time()
    end_time = time.perf_counter()

    duration_ms = (end_time - start_time) * 1000.0
    cpu_ms = (end_cpu - start_cpu) * 1000.0

    return BenchmarkResult(
        operation=f"Agent Query: {query[:50]}{'...' if len(query) > 50 else ''}",
        service="Agent",
        duration_ms=duration_ms,
        success=success,
        error=error,
        metadata=metadata,
        start_ns=start_ns,
        end_ns=end_ns,
        cpu_ms=cpu_ms,
    )


async def run_agent_performance_comparison(
    benchmarker: PerformanceBenchmarker, queries: List[str]
) -> None:
    """Compare agent performance across different query types."""
    s = benchmarker.style
    print(f"\n{s.reload()} Running Agent Performance Comparison...")

    simple_queries: List[str] = []
    complex_queries: List[str] = []

    for query in queries:
        text = query.lower()
        wc = len(query.split())
        has_filters = any(
            word in text for word in ["with", "above", "below", "from", "to", "that", "similar"]
        )
        has_multi = text.count(" and ") + text.count(" but ") + text.count(" or ") > 0
        if wc <= 5 and not has_filters and not has_multi:
            simple_queries.append(query)
        else:
            complex_queries.append(query)

    if simple_queries:
        simple_suite = benchmarker.create_suite("Simple Agent Queries (Comparison)")
        for query in simple_queries[:3]:
            r = await benchmark_agent_query(benchmarker, query)
            simple_suite.add_result(r)
        benchmarker.print_suite_summary(simple_suite)

    if complex_queries:
        complex_suite = benchmarker.create_suite("Complex Agent Queries (Comparison)")
        for query in complex_queries[:3]:
            r = await benchmark_agent_query(benchmarker, query)
            complex_suite.add_result(r)
        benchmarker.print_suite_summary(complex_suite)

    if simple_queries and complex_queries:
        simple_stats = benchmarker.suites.get(
            "Simple Agent Queries (Comparison)", BenchmarkSuite("")
        ).get_stats()
        complex_stats = benchmarker.suites.get(
            "Complex Agent Queries (Comparison)", BenchmarkSuite("")
        ).get_stats()

        if simple_stats and complex_stats:
            print(f"\n{s.chart()} Agent Query Complexity Comparison:")
            print(f"  Simple queries: {simple_stats['mean_ms']:.1f}ms average")
            print(f"  Complex queries: {complex_stats['mean_ms']:.1f}ms average")

            if complex_stats["mean_ms"] > simple_stats["mean_ms"]:
                factor = complex_stats["mean_ms"] / simple_stats["mean_ms"]
                print(f"  Complexity factor: {factor:.2f}x slower")
                if factor > 3.0:
                    print(
                        f"  {s.warn()} Complex queries are significantly slower - "
                        "consider optimization"
                    )
                elif factor > 2.0:
                    print(f"  {s.warn()} Complex queries are moderately slower")
                else:
                    print(
                        f"  {s.ok()} Query complexity has reasonable impact"
                    )


# ----------------------- Tool integration benchmarks -------------------


async def run_tool_integration_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    print(f"\n{s.wrench()} Running Tool Integration Benchmarks...")

    try:
        # Run independent tool suites in parallel to speed up iteration
        tasks = [
            run_tool_registry_benchmarks(benchmarker),
            run_plex_tool_benchmarks(benchmarker, args),
            run_tmdb_tool_benchmarks(benchmarker, args),
            run_radarr_tool_benchmarks(benchmarker, args),
            run_sonarr_tool_benchmarks(benchmarker, args),
            run_tool_cache_benchmarks(benchmarker),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"  {s.fail()} Tool integration benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()


async def run_tool_registry_benchmarks(
    benchmarker: PerformanceBenchmarker,
) -> None:
    s = benchmarker.style
    print("\n📋 Testing Tool Registry...")

    try:
        from bot.tools.registry_cache import (
            get_cached_registry,
            initialize_registry_cache,
        )
        from llm.clients import LLMClient

        api_key = (
            benchmarker.settings.openai_api_key
            or benchmarker.settings.openrouter_api_key
            or ""
        )
        if not api_key:
            print(f"  {s.warn()} Skipping tool registry tests - no LLM API key")
            return

        llm_client = LLMClient(api_key)

        def build_registry_wrapper(project_root, llm_client):
            initialize_registry_cache(project_root)
            return get_cached_registry(llm_client)

        registry_ops = [
            (
                "Build Tool Registry",
                "Registry",
                build_registry_wrapper,
                (benchmarker.project_root, llm_client),
                {},
            ),
        ]

        await benchmarker.run_benchmark_suite(
            "Tool Registry Operations",
            registry_ops,
            parallel=True,
            warmup=0,
        )

    except Exception as e:
        print(f"  {s.fail()} Tool registry benchmarks failed: {e}")


async def run_plex_tool_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print(f"  {s.warn()} Skipping Plex tool benchmarks - configuration missing")
        return

    print("\n📋 Testing Plex Tool Implementations...")

    try:
        from bot.tools.tool_impl_plex import (
            make_get_plex_library_sections,
            make_get_plex_recently_added,
            make_get_plex_unwatched,
            make_get_plex_on_deck,
        )

        get_sections = make_get_plex_library_sections(benchmarker.project_root)
        get_recent = make_get_plex_recently_added(benchmarker.project_root)
        get_unwatched = make_get_plex_unwatched(benchmarker.project_root)
        get_on_deck = make_get_plex_on_deck(benchmarker.project_root)

        tool_ops = [
            ("Get Library Sections Tool", "PlexTool", get_sections, ({},), {}),
            (
                "Get Recently Added Tool",
                "PlexTool",
                get_recent,
                ({"section_type": "movie", "limit": 5},),
                {},
            ),
            (
                "Get Unwatched Tool",
                "PlexTool",
                get_unwatched,
                ({"section_type": "movie", "limit": 5},),
                {},
            ),
            ("Get On Deck Tool", "PlexTool", get_on_deck, ({"limit": 5},), {}),
        ]

        await benchmarker.run_benchmark_suite(
            "Plex Tool Implementations", tool_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} Plex tool benchmarks failed: {e}")


async def run_tmdb_tool_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.tmdb_api_key:
        print(f"  {s.warn()} Skipping TMDb tool benchmarks - configuration missing")
        return

    print("\n📋 Testing TMDb Tool Implementations...")

    try:
        from bot.tools.tool_impl_tmdb import (
            make_tmdb_search,
            make_tmdb_popular_movies,
            make_tmdb_trending,
            make_tmdb_discover_movies,
        )

        tmdb_search = make_tmdb_search(benchmarker.project_root)
        tmdb_popular = make_tmdb_popular_movies(benchmarker.project_root)
        tmdb_trending = make_tmdb_trending(benchmarker.project_root)
        tmdb_discover = make_tmdb_discover_movies(benchmarker.project_root)

        tool_ops = [
            ("TMDb Search Tool", "TMDbTool", tmdb_search, ({"query": "inception"},), {}),
            ("TMDb Popular Movies Tool", "TMDbTool", tmdb_popular, ({"page": 1},), {}),
            (
                "TMDb Trending Tool",
                "TMDbTool",
                tmdb_trending,
                ({"media_type": "movie", "time_window": "week"},),
                {},
            ),
            (
                "TMDb Discover Movies Tool",
                "TMDbTool",
                tmdb_discover,
                ({"sort_by": "popularity.desc"},),
                {},
            ),
        ]

        await benchmarker.run_benchmark_suite(
            "TMDb Tool Implementations",
            tool_ops,
            parallel=True,
            warmup=args.warmup,
        )

    except Exception as e:
        print(f"  {s.fail()} TMDb tool benchmarks failed: {e}")


async def run_radarr_tool_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print(f"  {s.warn()} Skipping Radarr tool benchmarks - configuration missing")
        return

    print("\n📋 Testing Radarr Tool Implementations...")

    try:
        from bot.tools.tool_impl_radarr import (
            make_radarr_get_movies,
            make_radarr_get_queue,
            make_radarr_system_status,
        )

        get_movies = make_radarr_get_movies(benchmarker.project_root)
        get_queue = make_radarr_get_queue(benchmarker.project_root)
        get_status = make_radarr_system_status(benchmarker.project_root)

        tool_ops = [
            ("Radarr Get Movies Tool", "RadarrTool", get_movies, ({},), {}),
            ("Radarr Get Queue Tool", "RadarrTool", get_queue, ({},), {}),
            ("Radarr System Status Tool", "RadarrTool", get_status, ({},), {}),
        ]

        await benchmarker.run_benchmark_suite(
            "Radarr Tool Implementations",
            tool_ops,
            parallel=True,
            warmup=args.warmup,
        )

    except Exception as e:
        print(f"  {s.fail()} Radarr tool benchmarks failed: {e}")


async def run_sonarr_tool_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print(f"  {s.warn()} Skipping Sonarr tool benchmarks - configuration missing")
        return

    print("\n📋 Testing Sonarr Tool Implementations...")

    try:
        from bot.tools.tool_impl_sonarr import (
            make_sonarr_get_series,
            make_sonarr_get_queue,
            make_sonarr_system_status,
        )

        get_series = make_sonarr_get_series(benchmarker.project_root)
        get_queue = make_sonarr_get_queue(benchmarker.project_root)
        get_status = make_sonarr_system_status(benchmarker.project_root)

        tool_ops = [
            ("Sonarr Get Series Tool", "SonarrTool", get_series, ({},), {}),
            ("Sonarr Get Queue Tool", "SonarrTool", get_queue, ({},), {}),
            ("Sonarr System Status Tool", "SonarrTool", get_status, ({},), {}),
        ]

        await benchmarker.run_benchmark_suite(
            "Sonarr Tool Implementations",
            tool_ops,
            parallel=True,
            warmup=args.warmup,
        )

    except Exception as e:
        print(f"  {s.fail()} Sonarr tool benchmarks failed: {e}")


async def run_tool_cache_benchmarks(
    benchmarker: PerformanceBenchmarker,
) -> None:
    s = benchmarker.style
    print("\n📋 Testing Tool Result Caching...")

    try:
        from bot.tools.result_cache import put_tool_result, fetch_cached_result

        # We'll chain put -> get, so run sequential for dependency correctness.
        # Capture ref_id from put (if available) and use it in get.
        ref_holder: Dict[str, Optional[str]] = {"ref_id": None}

        def put_wrapper(data, ttl):
            rid = put_tool_result(data, ttl)
            # Try to capture the reference id if returned
            if isinstance(rid, str) and rid:
                ref_holder["ref_id"] = rid
            return {"ref_id": rid} if rid else {"ref_id": None}

        def get_wrapper():
            ref_id = ref_holder.get("ref_id")
            # Fall back to a likely-nonexistent id to test behavior
            ref_id = ref_id or "test_ref_id"
            return fetch_cached_result(ref_id)

        cache_ops = [
            ("Cache Put Operation", "Cache", put_wrapper, ({"test": "data"}, 60), {}),
            ("Cache Get Operation", "Cache", get_wrapper, (), {}),
        ]

        await benchmarker.run_benchmark_suite(
            "Tool Result Cache",
            cache_ops,
            parallel=False,  # dependency
            warmup=0,
        )

    except Exception as e:
        print(f"  {s.fail()} Tool cache benchmarks failed: {e}")


# ----------------------- Worker integration benchmarks -----------------


async def run_worker_integration_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    print(f"\n{s.gear()} Running Worker Integration Benchmarks...")

    try:
        # Run independent worker suites in parallel to accelerate coverage
        tasks = [
            run_plex_worker_benchmarks(benchmarker, args),
            run_tmdb_worker_benchmarks(benchmarker, args),
            run_radarr_worker_benchmarks(benchmarker, args),
            run_sonarr_worker_benchmarks(benchmarker, args),
            run_summarizer_worker_benchmarks(benchmarker, args),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"  {s.fail()} Worker integration benchmarks failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()


async def run_plex_worker_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.plex_base_url or not benchmarker.settings.plex_token:
        print(f"  {s.warn()} Skipping Plex worker benchmarks - configuration missing")
        return

    print("\n⚙️ Testing Plex Workers...")

    try:
        from bot.workers.plex import PlexWorker
        from bot.workers.plex_search import PlexSearchWorker

        plex_worker = PlexWorker(benchmarker.project_root)
        plex_search_worker = PlexSearchWorker(benchmarker.project_root)

        async def plex_get_sections():
            return await plex_worker.get_library_sections()

        async def plex_get_recent():
            return await plex_worker.get_recently_added(
                section_type="movie", limit=5, response_level="compact"
            )

        worker_ops = [
            (
                "Plex Worker - Get Library Sections",
                "PlexWorker",
                plex_get_sections,
                (),
                {},
            ),
            (
                "Plex Worker - Get Recently Added",
                "PlexWorker",
                plex_get_recent,
                (),
                {},
            ),
        ]

        await benchmarker.run_benchmark_suite(
            "Plex Workers", worker_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} Plex worker benchmarks failed: {e}")


async def run_tmdb_worker_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.tmdb_api_key:
        print(f"  {s.warn()} Skipping TMDb worker benchmarks - configuration missing")
        return

    print("\n⚙️ Testing TMDb Workers...")

    try:
        from bot.workers.tmdb import TMDbWorker

        tmdb_worker = TMDbWorker(benchmarker.project_root)

        async def tmdb_search():
            return await tmdb_worker.search_movie(query="inception")

        async def tmdb_popular():
            return await tmdb_worker.popular_movies(page=1)

        worker_ops = [
            ("TMDb Worker - Search Movies", "TMDbWorker", tmdb_search, (), {}),
            ("TMDb Worker - Get Popular Movies", "TMDbWorker", tmdb_popular, (), {}),
        ]

        await benchmarker.run_benchmark_suite(
            "TMDb Workers", worker_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} TMDb worker benchmarks failed: {e}")


async def run_radarr_worker_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.radarr_base_url or not benchmarker.settings.radarr_api_key:
        print(f"  {s.warn()} Skipping Radarr worker benchmarks - configuration missing")
        return

    print("\n⚙️ Testing Radarr Workers...")

    try:
        from bot.workers.radarr import RadarrWorker

        radarr_worker = RadarrWorker(benchmarker.project_root)

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

        await benchmarker.run_benchmark_suite(
            "Radarr Workers", worker_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} Radarr worker benchmarks failed: {e}")


async def run_sonarr_worker_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if not benchmarker.settings.sonarr_base_url or not benchmarker.settings.sonarr_api_key:
        print(f"  {s.warn()} Skipping Sonarr worker benchmarks - configuration missing")
        return

    print("\n⚙️ Testing Sonarr Workers...")

    try:
        from bot.workers.sonarr import SonarrWorker

        sonarr_worker = SonarrWorker(benchmarker.project_root)

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

        await benchmarker.run_benchmark_suite(
            "Sonarr Workers", worker_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} Sonarr worker benchmarks failed: {e}")


async def run_summarizer_worker_benchmarks(
    benchmarker: PerformanceBenchmarker, args
) -> None:
    s = benchmarker.style
    if (
        not benchmarker.settings.openai_api_key
        and not benchmarker.settings.openrouter_api_key
    ):
        print(f"  {s.warn()} Skipping summarizer worker benchmarks - no LLM API key")
        return

    print("\n⚙️ Testing Summarizer Workers...")

    try:
        from bot.workers.summarizer import SummarizerWorker

        api_key = (
            benchmarker.settings.openai_api_key
            or benchmarker.settings.openrouter_api_key
            or ""
        )
        if not api_key:
            print(f"  {s.warn()} Skipping summarizer worker tests - no LLM API key")
            return

        summarizer_worker = SummarizerWorker(api_key)

        async def summarize_test():
            try:
                result = await summarizer_worker.summarize_json(
                    benchmarker.project_root,
                    [{"title": "Test Movie", "year": 2023}],
                    schema_hint="movie_list",
                    target_chars=200,
                )
                return {"summary": result, "success": True}
            except Exception as e:
                return {"error": str(e), "success": False}

        worker_ops = [
            (
                "Summarizer Worker - Summarize JSON",
                "SummarizerWorker",
                summarize_test,
                (),
                {},
            ),
        ]

        await benchmarker.run_benchmark_suite(
            "Summarizer Workers", worker_ops, parallel=True, warmup=args.warmup
        )

    except Exception as e:
        print(f"  {s.fail()} Summarizer worker benchmarks failed: {e}")


# ------------------------------- Reporting -----------------------------


def _aggregate_services(
    suites: Dict[str, BenchmarkSuite]
) -> Dict[str, Dict[str, Any]]:
    """Aggregate stats by service across all suites."""
    service_map: Dict[str, List[float]] = {}
    failures: Dict[str, int] = {}

    for suite in suites.values():
        for r in suite.results:
            service_map.setdefault(r.service, [])
            failures.setdefault(r.service, 0)
            if r.success:
                service_map[r.service].append(r.duration_ms)
            else:
                failures[r.service] += 1

    def pct(data: List[float], p: float) -> float:
        if not data:
            return 0.0
        ds = sorted(data)
        k = (len(ds) - 1) * p
        f = int(k)
        c = min(f + 1, len(ds) - 1)
        if f == c:
            return ds[f]
        return ds[f] + (ds[c] - ds[f]) * (k - f)

    out: Dict[str, Dict[str, Any]] = {}
    for svc, durs in service_map.items():
        count = len(durs) + failures.get(svc, 0)
        succ = len(durs)
        fail = failures.get(svc, 0)
        if durs:
            out[svc] = {
                "success_count": succ,
                "failure_count": fail,
                "total_count": count,
                "mean_ms": round(statistics.mean(durs), 2),
                "median_ms": round(statistics.median(durs), 2),
                "p90_ms": round(pct(durs, 0.9), 2),
                "p95_ms": round(pct(durs, 0.95), 2),
                "p99_ms": round(pct(durs, 0.99), 2),
                "min_ms": round(min(durs), 2),
                "max_ms": round(max(durs), 2),
            }
        else:
            out[svc] = {
                "success_count": 0,
                "failure_count": fail,
                "total_count": count,
            }
    return out


def print_final_summary(benchmarker: PerformanceBenchmarker) -> None:
    """Print comprehensive final summary of all benchmark results."""
    s = benchmarker.style
    print("\n" + "=" * 60)
    print(f"{s.chart()} FINAL BENCHMARK SUMMARY")
    print("=" * 60)

    if not benchmarker.suites:
        print("No benchmark suites were executed.")
        return

    total_operations = 0
    total_successes = 0
    total_failures = 0
    slow_suites = 0

    for suite_name, suite in benchmarker.suites.items():
        stats = suite.get_stats()
        if stats and "success_count" in stats:
            total_operations += stats["success_count"] + stats["failure_count"]
            total_successes += stats["success_count"]
            total_failures += stats["failure_count"]

            threshold = benchmarker.slow_threshold_ms
            if "Agent" in suite_name:
                threshold = benchmarker.agent_complex_threshold_ms
            if "mean_ms" in stats and stats["mean_ms"] > threshold:
                slow_suites += 1

    if total_operations > 0:
        print(
            f"Total Operations: {total_operations}\n"
            f"Successful: {total_successes} "
            f"({(total_successes/total_operations)*100:.1f}%)\n"
            f"Failed: {total_failures} "
            f"({(total_failures/total_operations)*100:.1f}%)"
        )
    else:
        print("Total Operations: 0\nSuccessful: 0\nFailed: 0")

    print(
        f"Slow Suites (>= {benchmarker.slow_threshold_ms:.0f}ms mean): "
        f"{slow_suites}/{len(benchmarker.suites)}"
    )

    if slow_suites > 0:
        print(
            f"\n{ s.warn() } WARNING: {slow_suites} benchmark suite(s) "
            "exceeded their thresholds"
        )
        print(
            f"   - Standard threshold: {benchmarker.slow_threshold_ms:.0f}ms\n"
            f"   - Agent simple queries: "
            f"{benchmarker.agent_simple_threshold_ms/1000:.0f}s\n"
            f"   - Agent complex queries: "
            f"{benchmarker.agent_complex_threshold_ms/1000:.0f}s\n"
            "   Consider investigating bottlenecks in these areas."
        )

    print("\nPer-service summary:")
    services = _aggregate_services(benchmarker.suites)
    for svc, data in services.items():
        if "mean_ms" in data:
            print(
                f"  - {svc}: {data['success_count']}/{data['total_count']} "
                f"ok, {data['mean_ms']:.1f}ms avg "
                f"(p95 {data['p95_ms']:.1f}ms, max {data['max_ms']:.1f}ms)"
            )
        else:
            print(
                f"  - {svc}: {data['success_count']}/{data['total_count']} ok"
            )

    if benchmarker.verbose:
        # Show top 10 slowest successful ops overall
        all_results: List[BenchmarkResult] = []
        for suite in benchmarker.suites.values():
            all_results.extend([r for r in suite.results if r.success])
        top_slow = sorted(
            all_results, key=lambda r: r.duration_ms, reverse=True
        )[:10]
        if top_slow:
            print("\nTop slow operations:")
            for r in top_slow:
                print(
                    f"  - {r.operation} [{r.service}] "
                    f"{r.duration_ms:.1f}ms"
                )

    print("\nDetailed Results by Suite:")
    for suite_name, suite in benchmarker.suites.items():
        benchmarker.print_suite_summary(suite)


def _emit_json(
    benchmarker: PerformanceBenchmarker, path: str, meta: Dict[str, Any]
) -> None:
    data = {
        "meta": meta,
        "suites": [],
        "services": _aggregate_services(benchmarker.suites),
    }
    for name, suite in benchmarker.suites.items():
        data["suites"].append(
            {
                "name": name,
                "iterations": suite.iterations,
                "stats": suite.get_stats(),
                "results": [r.to_dict() for r in suite.results],
            }
        )
    Path(path).write_text(json.dumps(data, indent=2))
    print(f"  Wrote JSON report to {path}")


def _emit_csv(benchmarker: PerformanceBenchmarker, path: str) -> None:
    rows: List[Dict[str, Any]] = []
    for suite_name, suite in benchmarker.suites.items():
        for r in suite.results:
            row = {
                "suite": suite_name,
                "operation": r.operation,
                "service": r.service,
                "duration_ms": f"{r.duration_ms:.3f}",
                "success": r.success,
                "error": r.error or "",
                "start_ns": r.start_ns or 0,
                "end_ns": r.end_ns or 0,
                "cpu_ms": f"{(r.cpu_ms or 0.0):.3f}",
                "iteration": r.metadata.get("iteration", ""),
            }
            rows.append(row)

    fieldnames = [
        "suite",
        "operation",
        "service",
        "duration_ms",
        "success",
        "error",
        "start_ns",
        "end_ns",
        "cpu_ms",
        "iteration",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote CSV report to {path}")


def _emit_junit(benchmarker: PerformanceBenchmarker, path: str) -> None:
    try:
        import xml.etree.ElementTree as ET
    except Exception:
        print("  Skipping JUnit report (xml.etree not available)")
        return

    testsuites = ET.Element("testsuites")
    for suite_name, suite in benchmarker.suites.items():
        stats = suite.get_stats()
        tests = len(suite.results)
        failures = stats.get("failure_count", 0)
        ts = ET.SubElement(
            testsuites,
            "testsuite",
            name=suite_name,
            tests=str(tests),
            failures=str(failures),
        )
        for r in suite.results:
            tc = ET.SubElement(
                ts,
                "testcase",
                classname=r.service,
                name=r.operation,
                time=f"{r.duration_ms/1000.0:.3f}",
            )
            if not r.success:
                failure = ET.SubElement(tc, "failure", message=r.error or "Error")
                failure.text = r.error or "Error"

    tree = ET.ElementTree(testsuites)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"  Wrote JUnit report to {path}")


# --------------------------------- Main --------------------------------


async def _run_selected_services(benchmarker: PerformanceBenchmarker, args) -> None:
    """Run selected service benchmark groups, optionally in parallel."""
    tasks = []
    if args.parallel_services:
        if args.plex_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        ):
            tasks.append(run_plex_benchmarks(benchmarker, args))
        if args.radarr_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        ):
            tasks.append(run_radarr_benchmarks(benchmarker, args))
        if args.sonarr_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        ):
            tasks.append(run_sonarr_benchmarks(benchmarker, args))
        if args.tmdb_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        ):
            tasks.append(run_tmdb_benchmarks(benchmarker, args))
        if args.agent_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        ):
            if not args.skip_agent:
                tasks.append(run_agent_benchmarks(benchmarker, args))
        if tasks:
            await asyncio.gather(*tasks)
    else:
        # Sequential service execution
        test_plex = args.plex_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        )
        test_radarr = args.radarr_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        )
        test_sonarr = args.sonarr_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        )
        test_tmdb = args.tmdb_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        )
        test_agent = args.agent_only or not any(
            [args.plex_only, args.radarr_only, args.sonarr_only, args.tmdb_only, args.agent_only]
        )

        if test_plex:
            await run_plex_benchmarks(benchmarker, args)
        if test_radarr:
            await run_radarr_benchmarks(benchmarker, args)
        if test_sonarr:
            await run_sonarr_benchmarks(benchmarker, args)
        if test_tmdb:
            await run_tmdb_benchmarks(benchmarker, args)
        if test_agent and not args.skip_agent:
            await run_agent_benchmarks(benchmarker, args)


async def main() -> int:
    """Main entry point."""
    args = build_argparser().parse_args()

    # Validate arguments
    service_flags = [
        args.plex_only,
        args.radarr_only,
        args.sonarr_only,
        args.tmdb_only,
        args.agent_only,
    ]
    if sum(1 for f in service_flags if f) > 1:
        print("❌ Error: Only one service-specific flag can be used at a time")
        return 1
    if args.iterations < 1:
        print("❌ Error: Iterations must be at least 1")
        return 1
    if args.warmup < 0:
        print("❌ Error: Warmup must be >= 0")
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
        print("❌ Error: Agent simple threshold must be less than complex")
        return 1
    if args.concurrency < 1:
        print("❌ Error: Concurrency must be >= 1")
        return 1
    if args.op_timeout < 0:
        print("❌ Error: op-timeout must be >= 0")
        return 1

    s = Style(color=_supports_color() and not args.no_color, emoji=not args.no_emoji)

    print(f"{s.film()} MovieBot Performance Benchmarking Tool")
    print("=" * 50)
    print(f"Project root: {_PROJECT_ROOT}")
    print(f"Iterations: {args.iterations} (warmup: {args.warmup})")
    print(f"Concurrency: {args.concurrency}")
    print(
        f"Op timeout: "
        f"{(args.op_timeout if args.op_timeout else 0):.1f}s "
        f"(0 = unlimited)"
    )
    print(f"Slow threshold: {args.threshold}ms")
    print(f"Agent simple threshold: {args.agent_simple_threshold}s")
    print(f"Agent complex threshold: {args.agent_complex_threshold}s")
    print(f"Verbose: {args.verbose}")
    print(f"Parallel services: {args.parallel_services}")

    # Initialize benchmarker
    benchmarker = PerformanceBenchmarker(
        project_root=_PROJECT_ROOT,
        iterations=args.iterations,
        verbose=args.verbose,
        concurrency=args.concurrency,
        op_timeout_ms=int(args.op_timeout * 1000.0),
        no_color=args.no_color,
        no_emoji=args.no_emoji,
    )
    benchmarker.slow_threshold_ms = args.threshold
    benchmarker.agent_simple_threshold_ms = (
        args.agent_simple_threshold * 1000.0
    )
    benchmarker.agent_complex_threshold_ms = (
        args.agent_complex_threshold * 1000.0
    )

    # Determine which services to test (for printout only)
    test_plex = args.plex_only or not any(service_flags)
    test_radarr = args.radarr_only or not any(service_flags)
    test_sonarr = args.sonarr_only or not any(service_flags)
    test_tmdb = args.tmdb_only or not any(service_flags)
    test_agent = args.agent_only or not any(service_flags)

    print(f"\nServices to test: ", end="")
    services = []
    if test_plex:
        services.append("Plex")
    if test_radarr:
        services.append("Radarr")
    if test_sonarr:
        services.append("Sonarr")
    if test_tmdb:
        services.append("TMDb")
    if test_agent:
        services.append("Agent")
    print(", ".join(services))

    try:
        # Validate environment and configuration
        print("\n🔧 Validating environment and configuration...")
        validation_result = await validate_environment(benchmarker)
        if not validation_result:
            print(
                "❌ Environment validation failed. Please check your .env and configuration."
            )
            return 1

        # Run service-specific benchmarks (with optional parallelism)
        await _run_selected_services(benchmarker, args)

        # Run tool and worker integration tests
        if not args.skip_tools:
            await run_tool_integration_benchmarks(benchmarker, args)

        if not args.skip_workers:
            await run_worker_integration_benchmarks(benchmarker, args)

        # Print final summary
        print_final_summary(benchmarker)

        # Optional outputs
        meta = {
            "project_root": str(_PROJECT_ROOT),
            "iterations": args.iterations,
            "warmup": args.warmup,
            "concurrency": args.concurrency,
            "op_timeout_s": args.op_timeout,
            "threshold_ms": args.threshold,
            "agent_simple_threshold_s": args.agent_simple_threshold,
            "agent_complex_threshold_s": args.agent_complex_threshold,
            "parallel_services": args.parallel_services,
        }
        if args.output_json:
            _emit_json(benchmarker, args.output_json, meta)
        if args.output_csv:
            _emit_csv(benchmarker, args.output_csv)
        if args.junit:
            _emit_junit(benchmarker, args.junit)

        # Clean up resources
        await benchmarker.cleanup()

        # Exit code logic
        exit_code = 0
        if args.fail_on_error:
            any_fail = any(
                any(not r.success for r in suite.results)
                for suite in benchmarker.suites.values()
            )
            if any_fail:
                exit_code = 2
        if args.fail_on_slow and exit_code == 0:
            any_slow = False
            for suite_name, suite in benchmarker.suites.items():
                st = suite.get_stats()
                if not st or st.get("success_count", 0) == 0:
                    continue
                thr = benchmarker.slow_threshold_ms
                if "Agent" in suite_name:
                    thr = benchmarker.agent_complex_threshold_ms
                if st.get("mean_ms", 0) > thr:
                    any_slow = True
                    break
            if any_slow:
                exit_code = 3

        if exit_code == 0:
            print(f"\n{s.ok()} Benchmarking complete!")
        else:
            print(f"\n{s.warn()} Benchmarking complete with issues (exit {exit_code})")
        return exit_code

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