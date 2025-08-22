#!/usr/bin/env python3
"""
Example script demonstrating OpenRouter integration with MovieBot.

This script shows how to use the GLM 4.5 Air model through OpenRouter
for various LLM tasks.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from llm.clients import LLMClient


def main():
    """Demonstrate OpenRouter integration."""
    # Load environment variables
    load_dotenv(project_root / ".env")
    
    # Check if OpenRouter API key is available
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        print("❌ OPENROUTER_API_KEY not found in .env file")
        print("Please add your OpenRouter API key to the .env file")
        return
    
    print("🚀 Testing OpenRouter integration with GLM 4.5 Air...")
    
    # Initialize OpenRouter client
    client = LLMClient(openrouter_api_key, provider="openrouter")
    
    # Test basic chat functionality
    print("\n📝 Testing basic chat...")
    try:
        response = client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[
                {"role": "user", "content": "Hello! What can you tell me about yourself?"}
            ],
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        print(f"✅ Response: {content}")
        
    except Exception as e:
        print(f"❌ Chat test failed: {e}")
        return
    
    # Test token counting
    print("\n🔢 Testing token counting...")
    try:
        messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"}
        ]
        token_count = client.count_tokens(messages)
        print(f"✅ Token count: {token_count}")
        
    except Exception as e:
        print(f"❌ Token counting failed: {e}")
    
    # Test with a more complex prompt
    print("\n🎬 Testing movie recommendation prompt...")
    try:
        response = client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful movie recommendation assistant. Provide brief, engaging recommendations."
                },
                {
                    "role": "user", 
                    "content": "I'm in the mood for a sci-fi movie. What would you recommend?"
                }
            ],
            temperature=0.8
        )
        
        content = response.choices[0].message.content
        print(f"✅ Movie recommendation: {content}")
        
    except Exception as e:
        print(f"❌ Movie recommendation test failed: {e}")
    
    print("\n🎉 OpenRouter integration test completed!")
    print("\nTo use OpenRouter in your MovieBot:")
    print("1. Ensure OPENROUTER_API_KEY is set in your .env file")
    print("2. The bot will automatically use OpenRouter when available")
    print("3. Available models include: z-ai/glm-4.5-air:free")


if __name__ == "__main__":
    main()
