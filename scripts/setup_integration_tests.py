#!/usr/bin/env python3
"""
Setup script for integration tests.

This script helps configure the environment for running integration tests
against a real Plex server using the same .env file as the main program.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def load_env_file():
    """Load environment variables from .env file."""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✅ Loaded environment from {env_file}")
        return True
    else:
        print(f"❌ No .env file found at {env_file}")
        return False


def check_environment():
    """Check if the environment is properly configured for integration tests."""
    print("🔍 Checking integration test environment...")
    
    # Load from .env file first
    if not load_env_file():
        return False
    
    # Check required environment variables
    plex_url = os.getenv("PLEX_BASE_URL")
    plex_token = os.getenv("PLEX_TOKEN")
    
    if not plex_url:
        print("❌ PLEX_BASE_URL not found in .env file")
        return False
    
    if not plex_token:
        print("❌ PLEX_TOKEN not found in .env file")
        return False
    
    print(f"✅ PLEX_BASE_URL: {plex_url}")
    print(f"✅ PLEX_TOKEN: {'*' * min(len(plex_token), 8)}...")
    
    return True


def test_plex_connection():
    """Test connection to the Plex server."""
    print("\n🔗 Testing Plex server connection...")
    
    try:
        from integrations.plex_client import PlexClient
        
        plex_url = os.getenv("PLEX_BASE_URL")
        plex_token = os.getenv("PLEX_TOKEN")
        
        client = PlexClient(plex_url, plex_token)
        
        # Test basic connectivity
        sections = client.get_library_sections()
        
        print(f"✅ Successfully connected to Plex server")
        print(f"✅ Found {len(sections)} library sections:")
        
        for name, info in sections.items():
            print(f"   - {name}: {info['type']} ({info['count']} items)")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to Plex server: {e}")
        return False


def show_test_commands():
    """Show commands for running integration tests."""
    print("\n🚀 Integration test commands:")
    print("-" * 50)
    
    print("1. Run all integration tests (uses .env file):")
    print("   python run_tests.py --integration")
    
    print("\n2. Run specific integration test file:")
    print("   python run_tests.py --integration tests/test_plex_integration.py")
    
    print("\n3. Run with coverage:")
    print("   python run_tests.py --integration --coverage")
    
    print("\n4. Run with verbose output:")
    print("   python run_tests.py --integration --verbose")
    
    print("\n5. Override .env settings with command line:")
    print("   python run_tests.py --integration --plex-url http://custom-server:32400 --plex-token custom_token")
    
    print("\n6. Run only unit tests (no integration):")
    print("   python run_tests.py")
    
    print("\n7. Run quick unit tests:")
    print("   python run_tests.py --quick")
    
    print("\n8. Direct pytest commands:")
    print("   pytest tests/ -v -m integration  # Integration tests only")
    print("   pytest tests/ -v -m 'not integration'  # Unit tests only")


def show_env_file_info():
    """Show information about the .env file setup."""
    print("\n📁 .env File Configuration:")
    print("-" * 50)
    
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        print(f"✅ .env file found at: {env_file}")
        
        # Show the structure (without revealing sensitive data)
        with open(env_file, 'r') as f:
            lines = f.readlines()
        
        print("📋 .env file contains:")
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    if 'TOKEN' in key.upper() or 'PASSWORD' in key.upper() or 'SECRET' in key.upper():
                        print(f"   {key}=***hidden***")
                    else:
                        print(f"   {key}={value}")
                else:
                    print(f"   {line}")
    else:
        print(f"❌ No .env file found at: {env_file}")
        print("💡 Create a .env file with your Plex configuration:")
        print("   PLEX_BASE_URL=http://your-plex-server:32400")
        print("   PLEX_TOKEN=your_plex_token_here")


def main():
    """Main setup function."""
    print("🎬 MovieBot Integration Test Setup")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path("tests/").exists():
        print("❌ Error: No 'tests/' directory found. Run this script from the project root.")
        return 1
    
    # Check environment
    if not check_environment():
        print("\n💡 To set up the environment:")
        print("1. Ensure you have a .env file in your project root")
        print("2. Add PLEX_BASE_URL and PLEX_TOKEN to your .env file")
        print("3. Run this script again")
        return 1
    
    # Show .env file information
    show_env_file_info()
    
    # Test connection
    if not test_plex_connection():
        print("\n💡 Check your Plex server configuration in .env file and try again.")
        return 1
    
    # Show test commands
    show_test_commands()
    
    print("\n✅ Integration test setup complete!")
    print("Your .env file is properly configured and Plex server is accessible.")
    print("You can now run integration tests using the commands above.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
