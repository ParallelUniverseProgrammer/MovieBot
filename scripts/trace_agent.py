from __future__ import annotations

import asyncio
import json
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

import sys as _sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from config.loader import load_settings
from bot.agent import Agent


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


async def run_once(user_message: str, max_events: int, pretty: bool) -> int:
    project_root = _PROJECT_ROOT
    settings = load_settings(project_root)
    api_key = settings.openai_api_key or settings.openrouter_api_key or ""

    events: List[Dict[str, Any]] = []

    def progress_callback(kind: str, detail: str) -> None:
        # Store and also print as we go
        try:
            events.append({"kind": kind, "detail": detail})
            _print_event(kind, detail)
        except Exception:
            pass

    agent = Agent(api_key=api_key, project_root=project_root, progress_callback=progress_callback)

    msgs = [{"role": "user", "content": user_message}]

    try:
        resp = await agent.aconverse(msgs)
    except Exception as e:
        resp = {"error": str(e)}

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

    # Return 0 even if model errored; caller inspects output
    return 0


def main(argv: List[str]) -> int:
    args = _build_argparser().parse_args(argv)
    return asyncio.run(run_once(args.message, args.max_events, args.pretty))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


