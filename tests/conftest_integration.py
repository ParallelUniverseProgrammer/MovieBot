"""
Configuration for integration tests that run against real Plex servers.

This file provides fixtures and configuration for testing against actual
Plex instances rather than mocked ones.
"""

import pytest
import os
from pathlib import Path
from dotenv import load_dotenv


def pytest_addoption(parser):
    """Add command line options for integration tests."""
    parser.addoption(
        "--plex-url",
        action="store",
        default=None,
        help="Plex server URL for integration tests (overrides .env)"
    )
    parser.addoption(
        "--plex-token",
        action="store",
        default=None,
        help="Plex server token for integration tests (overrides .env)"
    )


def pytest_collection_modifyitems(config, items):
    """Mark integration tests to be skipped unless integration marker is specified."""
    # Check if any integration tests are being run
    has_integration_marker = any(
        "integration" in item.keywords for item in items
    )
    
    if has_integration_marker:
        # If integration tests exist, check if they should be run
        # Integration tests will be selected by the -m integration marker
        pass
    else:
        # No integration tests in the collection, nothing to modify
        pass


def pytest_configure(config):
    """Load environment variables from .env file before tests run."""
    # Load .env file from project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
    else:
        print(f"⚠️  No .env file found at {env_file}")


@pytest.fixture(scope="session")
def integration_config():
    """Get integration test configuration from .env file and command line options."""
    config = {
        "plex_url": None,
        "plex_token": None,
        "run_integration": False
    }
    
    # Check command line options first (these override .env)
    # Integration tests are selected by the -m integration marker
    config["run_integration"] = True  # If this fixture is called, integration tests are running
    
    config["plex_url"] = pytest.config.getoption("--plex-url")
    config["plex_token"] = pytest.config.getoption("--plex-token")
    
    # Fall back to environment variables (loaded from .env)
    if not config["plex_url"]:
        config["plex_url"] = os.getenv("PLEX_BASE_URL")
    if not config["plex_token"]:
        config["plex_token"] = os.getenv("PLEX_TOKEN")
    
    return config


@pytest.fixture(scope="session")
def integration_requirements_met(integration_config):
    """Check if all requirements for integration tests are met."""
    if not integration_config["run_integration"]:
        pytest.skip("Integration tests not requested")
    
    if not integration_config["plex_url"]:
        pytest.skip("Plex URL not provided (check .env file or use --plex-url)")
    
    if not integration_config["plex_token"]:
        pytest.skip("Plex token not provided (check .env file or use --plex-token)")
    
    return True


@pytest.fixture(scope="session")
def test_environment():
    """Get information about the test environment."""
    return {
        "python_version": os.sys.version,
        "platform": os.sys.platform,
        "project_root": str(Path(__file__).parent.parent),
        "test_type": "integration",  # This fixture is only used in integration tests
        "env_file_loaded": bool(os.getenv("PLEX_BASE_URL") or os.getenv("PLEX_TOKEN"))
    }
