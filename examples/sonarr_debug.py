#!/usr/bin/env python3
"""
Sonarr Client Debug Script

This script helps debug Sonarr connection issues and test the add_series functionality.
Run this to verify your Sonarr configuration and test adding shows.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from integrations.sonarr_client import SonarrClient


async def test_sonarr_connection():
    """Test basic Sonarr connection and get system info."""
    # Load environment variables from .env file
    load_dotenv()
    sonarr_url = os.getenv("SONARR_BASE_URL")
    sonarr_api_key = os.getenv("SONARR_API_KEY")
    
    if not sonarr_url or not sonarr_api_key:
        print("❌ Missing Sonarr configuration:")
        print(f"   SONARR_URL: {sonarr_url or 'NOT SET'}")
        print(f"   SONARR_API_KEY: {sonarr_api_key or 'NOT SET'}")
        print("\nPlease set these environment variables and try again.")
        return None
    
    print(f"🔗 Connecting to Sonarr at: {sonarr_url}")
    
    try:
        client = SonarrClient(sonarr_url, sonarr_api_key)
        
        # Test basic connection
        print("📡 Testing connection...")
        status = await client.system_status()
        print(f"✅ Connected! Sonarr version: {status.get('version', 'Unknown')}")
        
        # Get system health
        print("\n🏥 System Health:")
        health = await client.health()
        if health:
            for issue in health:
                print(f"   ⚠️  {issue.get('message', 'Unknown issue')}")
        else:
            print("   ✅ All systems healthy")
        
        # Get available quality profiles
        print("\n🎬 Quality Profiles:")
        profiles = await client.get_quality_profile_names()
        for profile in profiles:
            print(f"   ID {profile['id']}: {profile['name']}")
        
        # Get root folders
        print("\n📁 Root Folders:")
        folders = await client.get_root_folder_paths()
        for folder in folders:
            print(f"   {folder}")
        
        return client
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


async def test_add_series(client: SonarrClient):
    """Test adding a series with validation."""
    print("\n🧪 Testing Series Addition...")
    
    # Example: Breaking Bad (TVDB ID: 81189)
    test_tvdb_id = 81189
    test_series_name = "Breaking Bad"
    
    print(f"📺 Testing with: {test_series_name} (TVDB ID: {test_tvdb_id})")
    
    try:
        # First, validate the parameters using actual config values
        print("🔍 Validating parameters...")
        
        # Load config to get actual values
        from config.loader import load_runtime_config
        config = load_runtime_config(project_root)
        quality_profile_id = config.get("sonarr", {}).get("qualityProfileId", 4)
        root_folder_path = config.get("sonarr", {}).get("rootFolderPath", "C:\\Video\\TV")
        
        print(f"   Using quality profile ID: {quality_profile_id}")
        print(f"   Using root folder path: {root_folder_path}")
        
        await client._validate_add_series_params(
            tvdb_id=test_tvdb_id,
            quality_profile_id=quality_profile_id,
            root_folder_path=root_folder_path
        )
        print("✅ Parameters validated successfully")
        
        # Note: We won't actually add the series in this test
        # to avoid cluttering your Sonarr instance
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        print("\n💡 This helps identify the specific issue:")
        if "Quality profile ID" in str(e):
            print("   - Check your quality profile IDs")
        elif "Root folder path" in str(e):
            print("   - Check your root folder paths")
        elif "TVDB ID" in str(e):
            print("   - Check if the TVDB ID is valid")


async def main():
    """Main debug function."""
    print("🔧 Sonarr Client Debug Tool")
    print("=" * 40)
    
    # Test connection
    client = await test_sonarr_connection()
    if not client:
        return
    
    # Test series addition validation
    await test_add_series(client)
    
    # Clean up
    await client.close()
    
    print("\n✨ Debug complete!")
    print("\n💡 If you're still getting 400 errors, check:")
    print("   1. Your Sonarr version (this client supports v3)")
    print("   2. The exact error message from the validation")
    print("   3. Your quality profile IDs and root folder paths")


if __name__ == "__main__":
    asyncio.run(main())
