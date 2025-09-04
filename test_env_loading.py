#!/usr/bin/env python3
"""Test environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
project_root = Path(__file__).parent
env_path = project_root / ".env"
load_dotenv(env_path)

print("Environment variables:")
print(f"PLEX_BASE_URL: {os.getenv('PLEX_BASE_URL')}")
print(f"PLEX_TOKEN: {os.getenv('PLEX_TOKEN')}")
print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')}")

# Test settings loading
from config.loader import load_settings
settings = load_settings(project_root)
print(f"\nSettings:")
print(f"plex_base_url: {settings.plex_base_url}")
print(f"plex_token: {settings.plex_token}")
print(f"openai_api_key: {settings.openai_api_key}")
