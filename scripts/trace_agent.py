from __future__ import annotations

import asyncio
import json
import sys
import argparse
import time
import psutil
import os
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

import sys as _sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_settings
from bot.agent import Agent
from bot.tools.registry_cache import initialize_registry_cache


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the MovieBot agent once and capture a live progress trace."
    )
    p.add_argument(
        "--message",
        "-m",
        default="Add The Matrix (1999) to my Radarr",
        help="User message to send to the agent",
    )
    p.add_argument(
        "--max-events",
        type=int,
        default=300,
        help="Limit the number of events printed in the JSON trace (from the end)",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the final response object (if not plain text)",
    )
    p.add_argument(
        "--profile",
        action="store_true",
        help="Enable detailed performance profiling and timing analysis",
    )
    return p


def _print_event(kind: str, detail: str) -> None:
    # Single-line humanized progress output for live visibility
    try:
        clean = (detail or "").replace("\n", " ").strip()
        if len(clean) > 240:
            clean = clean[:237] + "…"
        print(f"[{kind}] {clean}")
    except Exception:
        pass


class PerformanceProfiler:
    """Comprehensive performance profiler for agent execution analysis."""
    
    def __init__(self, enable_profiling: bool = False):
        self.enable_profiling = enable_profiling
        self.timings: Dict[str, float] = {}
        self.memory_samples: List[Dict[str, Any]] = []
        self.llm_calls: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.process = psutil.Process(os.getpid())
        self.start_time = time.perf_counter()
        self.agent_events: List[Dict[str, Any]] = []
        
    def mark(self, name: str) -> None:
        """Mark a timing checkpoint."""
        if not self.enable_profiling:
            return
        current_time = time.perf_counter()
        self.timings[name] = current_time - self.start_time
        
        # Sample memory usage
        try:
            memory_info = self.process.memory_info()
            self.memory_samples.append({
                "checkpoint": name,
                "timestamp": current_time - self.start_time,
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "cpu_percent": self.process.cpu_percent()
            })
        except Exception:
            pass
    
    def record_llm_call(self, model: str, duration_ms: float, tokens_in: int = 0, tokens_out: int = 0) -> None:
        """Record LLM API call details."""
        if not self.enable_profiling:
            return
        self.llm_calls.append({
            "model": model,
            "duration_ms": duration_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "timestamp": time.perf_counter() - self.start_time
        })
    
    def record_tool_call(self, tool_name: str, duration_ms: float, success: bool, error: str = None) -> None:
        """Record tool execution details."""
        if not self.enable_profiling:
            return
        self.tool_calls.append({
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success,
            "error": error,
            "timestamp": time.perf_counter() - self.start_time
        })

    def record_agent_event(self, kind: str, detail: str) -> None:
        if not self.enable_profiling:
            return
        self.agent_events.append({
            "kind": kind,
            "detail": detail,
            "timestamp": time.perf_counter() - self.start_time,
        })
    
    def get_duration(self, start_name: str, end_name: str) -> float:
        """Get duration between two checkpoints."""
        if not self.enable_profiling:
            return 0.0
        return self.timings.get(end_name, 0) - self.timings.get(start_name, 0)
    
    def print_summary(self) -> None:
        """Print comprehensive performance summary."""
        if not self.enable_profiling:
            return
            
        print("\n" + "="*80)
        print("PERFORMANCE PROFILING SUMMARY")
        print("="*80)
        
        # Overall timing
        total_time = time.perf_counter() - self.start_time
        print(f"Total Execution Time: {total_time:.3f}s")
        
        # Phase breakdown
        phases = [
            ("startup", "imports"),
            ("imports", "settings_load"),
            ("settings_load", "registry_init"),
            ("registry_init", "agent_create"),
            ("agent_create", "agent_converse"),
            ("agent_converse", "cleanup")
        ]
        
        print("\nPhase Breakdown:")
        for start, end in phases:
            duration = self.get_duration(start, end)
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            print(f"  {start} → {end}: {duration:.3f}s ({percentage:.1f}%)")
        
        # LLM Call Analysis
        if self.llm_calls:
            print(f"\nLLM Call Analysis:")
            total_llm_time = sum(call["duration_ms"] for call in self.llm_calls) / 1000
            print(f"  Total LLM Calls: {len(self.llm_calls)}")
            print(f"  Total LLM Time: {total_llm_time:.3f}s ({total_llm_time/total_time*100:.1f}% of total)")
            print(f"  Average LLM Call: {total_llm_time/len(self.llm_calls):.3f}s")
            
            # Group by model
            model_stats = {}
            for call in self.llm_calls:
                model = call["model"]
                if model not in model_stats:
                    model_stats[model] = {"count": 0, "total_time": 0}
                model_stats[model]["count"] += 1
                model_stats[model]["total_time"] += call["duration_ms"] / 1000
            
            for model, stats in model_stats.items():
                avg_time = stats["total_time"] / stats["count"]
                print(f"    {model}: {stats['count']} calls, {stats['total_time']:.3f}s total, {avg_time:.3f}s avg")
        
        # Tool Call Analysis
        if self.tool_calls:
            print(f"\nTool Call Analysis:")
            total_tool_time = sum(call["duration_ms"] for call in self.tool_calls) / 1000
            successful_calls = sum(1 for call in self.tool_calls if call["success"])
            print(f"  Total Tool Calls: {len(self.tool_calls)}")
            print(f"  Successful Calls: {successful_calls}")
            print(f"  Total Tool Time: {total_tool_time:.3f}s ({total_tool_time/total_time*100:.1f}% of total)")
            print(f"  Average Tool Call: {total_tool_time/len(self.tool_calls):.3f}s")
            
            # Group by tool
            tool_stats = {}
            for call in self.tool_calls:
                tool = call["tool_name"]
                if tool not in tool_stats:
                    tool_stats[tool] = {"count": 0, "total_time": 0, "successes": 0}
                tool_stats[tool]["count"] += 1
                tool_stats[tool]["total_time"] += call["duration_ms"] / 1000
                if call["success"]:
                    tool_stats[tool]["successes"] += 1
            
            for tool, stats in tool_stats.items():
                avg_time = stats["total_time"] / stats["count"]
                success_rate = stats["successes"] / stats["count"] * 100
                print(f"    {tool}: {stats['count']} calls, {stats['total_time']:.3f}s total, {avg_time:.3f}s avg, {success_rate:.1f}% success")
        
        # Memory usage
        if self.memory_samples:
            print(f"\nMemory Usage:")
            peak_memory = max(sample["rss_mb"] for sample in self.memory_samples)
            final_memory = self.memory_samples[-1]["rss_mb"] if self.memory_samples else 0
            print(f"  Peak RSS: {peak_memory:.1f} MB")
            print(f"  Final RSS: {final_memory:.1f} MB")
        
        # Detailed checkpoints
        print(f"\nDetailed Checkpoints:")
        for name, timestamp in sorted(self.timings.items()):
            print(f"  {name}: {timestamp:.3f}s")
        
        print("="*80)


async def run_once(user_message: str, max_events: int, pretty: bool, profile: bool = False) -> int:
    # Initialize profiler
    profiler = PerformanceProfiler(enable_profiling=profile)
    profiler.mark("startup")
    
    project_root = _PROJECT_ROOT
    profiler.mark("imports")
    
    settings = load_settings(project_root)
    profiler.mark("settings_load")
    
    api_key = settings.openai_api_key or settings.openrouter_api_key or ""

    # Initialize the registry cache
    initialize_registry_cache(project_root)
    profiler.mark("registry_init")

    events: List[Dict[str, Any]] = []
    llm_start_stack: List[Dict[str, Any]] = []
    tool_start_times: Dict[str, List[float]] = defaultdict(list)

    def progress_callback(kind: str, detail: str) -> None:
        # Store and also print as we go
        try:
            events.append({"kind": kind, "detail": detail, "ts": time.perf_counter()})
            if profile:
                profiler.record_agent_event(kind, detail)
            _print_event(kind, detail)
            
            # Extract timing data from the humanized messages for profiling
            if profile:
                # Parse timing information from the humanized messages
                if kind == "llm.start":
                    # Extract model from message like "Consulting gpt-4.1-nano to sketch..."
                    if "Consulting" in detail and "to sketch" in detail:
                        model = detail.split("Consulting ")[1].split(" to sketch")[0]
                        llm_start_stack.append({"t": time.perf_counter(), "model": model})
                elif kind == "llm.finish":
                    # Calculate LLM call duration
                    if llm_start_stack:
                        start_info = llm_start_stack.pop()
                        duration_ms = (time.perf_counter() - start_info["t"]) * 1000
                        profiler.record_llm_call(start_info.get("model", "unknown"), duration_ms)
                elif kind == "tool.start":
                    # Extract tool name from message like "Starting TMDb search (tmdb_search) to advance..."
                    if "Starting" in detail and "(" in detail and ")" in detail:
                        tool_name = detail.split("(")[1].split(")")[0]
                        tool_start_times[tool_name].append(time.perf_counter())
                elif kind == "tool.finish":
                    # Calculate tool call duration and extract timing from message
                    tool_name = None
                    if "(" in detail and ")" in detail:
                        try:
                            tool_name = detail.split("(")[1].split(")")[0]
                        except Exception:
                            tool_name = None
                    if tool_name and tool_start_times.get(tool_name):
                        start_t = tool_start_times[tool_name].pop()
                        duration_ms = (time.perf_counter() - start_t) * 1000
                        profiler.record_tool_call(tool_name, duration_ms, True)
                elif kind == "tool.error":
                    # Handle tool errors
                    tool_name = None
                    if "(" in detail and ")" in detail:
                        try:
                            tool_name = detail.split("(")[1].split(")")[0]
                        except Exception:
                            tool_name = None
                    if tool_name and tool_start_times.get(tool_name):
                        start_t = tool_start_times[tool_name].pop()
                        duration_ms = (time.perf_counter() - start_t) * 1000
                        profiler.record_tool_call(tool_name, duration_ms, False, "tool error")
        except Exception:
            pass

    agent = Agent(api_key=api_key, project_root=project_root, progress_callback=progress_callback)
    profiler.mark("agent_create")

    msgs = [{"role": "user", "content": user_message}]

    try:
        resp = await agent.aconverse(msgs)
    except Exception as e:
        resp = {"error": str(e)}
    
    profiler.mark("agent_converse")

    print("\n=== TRACE (tail) ===")
    tail = events[-max_events:]
    print(json.dumps(tail, indent=2))

    print("\n=== RESPONSE ===")
    try:
        if isinstance(resp, dict):
            print(json.dumps(resp, indent=2) if pretty else resp)
        elif hasattr(resp, "choices"):
            # SDK object shape (OpenAI-compatible)
            content = getattr(getattr(resp.choices[0], "message", {}), "content", "")
            print(content or "<no content>")
        else:
            print(str(resp))
    except Exception:
        print(str(resp))

    # Best-effort resource cleanup to avoid aiohttp warnings
    try:
        await agent.aclose()
    except Exception:
        pass
    
    profiler.mark("cleanup")
    
    # Print performance summary if profiling enabled
    profiler.print_summary()

    # Return 0 even if model errored; caller inspects output
    return 0


def main(argv: List[str]) -> int:
    args = _build_argparser().parse_args(argv)
    return asyncio.run(run_once(args.message, args.max_events, args.pretty, args.profile))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


