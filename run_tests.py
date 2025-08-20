#!/usr/bin/env python3
"""
Simple test runner for MovieBot test suite.
Run this script to execute all tests or specific test categories.
"""

import sys
import subprocess
import argparse
from pathlib import Path
from dotenv import load_dotenv


def load_environment():
    """Load environment variables from .env file."""
    project_root = Path(__file__).parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
        return True
    else:
        print(f"⚠️  No .env file found at {env_file}")
        return False


def run_tests(test_pattern=None, verbose=False, coverage=False, integration=False, plex_url=None, plex_token=None):
    """Run the test suite with the specified options."""
    cmd = ["python", "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend(["--cov=bot", "--cov=integrations", "--cov-report=term-missing"])
    
    if integration:
        # Use pytest markers instead of custom arguments
        cmd.extend(["-m", "integration"])
        # Set environment variables for integration tests
        if plex_url:
            cmd.extend(["--plex-url", plex_url])
        if plex_token:
            cmd.extend(["--plex-token", plex_token])
    
    if test_pattern:
        cmd.append(test_pattern)
    else:
        cmd.append("tests/")
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        result = subprocess.run(cmd, check=True)
        print("-" * 50)
        print("✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print("-" * 50)
        print(f"❌ Tests failed with exit code {e.returncode}")
        return e.returncode


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description="Run MovieBot test suite")
    parser.add_argument(
        "--pattern", "-p",
        help="Test pattern to run (e.g., 'tests/test_plex_client.py')"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Run tests with verbose output"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Run tests with coverage reporting"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only essential tests quickly"
    )
    parser.add_argument(
        "--integration", "-i",
        action="store_true",
        help="Run integration tests against real Plex server (uses .env file)"
    )
    parser.add_argument(
        "--plex-url",
        help="Plex server URL for integration tests (overrides .env)"
    )
    parser.add_argument(
        "--plex-token",
        help="Plex server token for integration tests (overrides .env)"
    )
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not Path("tests/").exists():
        print("❌ Error: No 'tests/' directory found. Run this script from the project root.")
        return 1
    
    # Load environment variables from .env file
    load_environment()
    
    # Quick test mode
    if args.quick:
        print("🚀 Running quick test suite...")
        return run_tests("tests/test_plex_client.py", args.verbose, args.coverage)
    
    # Integration test mode
    if args.integration:
        print("🔗 Running integration tests against real Plex server...")
        print("ℹ️   Using pytest 'integration' marker to select tests")
        if not args.plex_url and not args.plex_token:
            print("ℹ️   Using Plex configuration from .env file")
        else:
            print("ℹ️   Using Plex configuration from command line arguments")
        return run_tests(args.pattern, args.verbose, args.coverage, True, args.plex_url, args.plex_token)
    
    # Full test suite
    print("🧪 Running MovieBot test suite...")
    return run_tests(args.pattern, args.verbose, args.coverage)


if __name__ == "__main__":
    sys.exit(main())
