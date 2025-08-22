#!/usr/bin/env python3
"""
Example demonstrating async LLM usage in MovieBot.

This script shows how to use the new async LLM methods for non-blocking operations.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from llm.clients import LLMClient
from bot.agent import Agent


async def demo_async_llm():
    """Demonstrate async LLM usage."""
    print("🚀 MovieBot Async LLM Demo")
    print("=" * 40)
    
    # Load environment variables
    load_dotenv()
    
    # Initialize LLM client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return
    
    # Test direct async LLM calls
    print("\n1. Testing direct async LLM calls...")
    llm_client = LLMClient(api_key, provider="openai")
    
    messages = [
        {"role": "user", "content": "Hello! What's 2+2? Answer in one word."}
    ]
    
    try:
        # Async call - non-blocking
        response = await llm_client.achat(
            model="gpt-5-nano",
            messages=messages,
            temperature=0.7
        )
        
        content = response.choices[0].message.content
        print(f"✅ LLM Response: {content}")
        
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
    
    # Test async agent
    print("\n2. Testing async agent...")
    project_root = Path(__file__).parent.parent
    
    try:
        agent = Agent(
            api_key=api_key,
            project_root=project_root,
            provider="openai"
        )
        
        # Async conversation - non-blocking
        response = await agent.aconverse([
            {"role": "user", "content": "What's the weather like today? Keep it brief."}
        ])
        
        content = response.choices[0].message.content
        print(f"✅ Agent Response: {content}")
        
    except Exception as e:
        print(f"❌ Agent call failed: {e}")
    
    # Test concurrent LLM calls
    print("\n3. Testing concurrent LLM calls...")
    
    async def make_concurrent_calls():
        tasks = []
        for i in range(3):
            task = llm_client.achat(
                model="gpt-5-nano",
                messages=[{"role": "user", "content": f"Count to {i+1} in words."}],
                temperature=0.7
            )
            tasks.append(task)
        
        # Execute all calls concurrently
        responses = await asyncio.gather(*tasks)
        
        for i, response in enumerate(responses):
            content = response.choices[0].message.content
            print(f"   Call {i+1}: {content}")
    
    try:
        await make_concurrent_calls()
        print("✅ Concurrent calls completed successfully!")
        
    except Exception as e:
        print(f"❌ Concurrent calls failed: {e}")


async def demo_openrouter_async():
    """Demonstrate async OpenRouter usage."""
    print("\n4. Testing OpenRouter async...")
    
    load_dotenv()
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if not openrouter_key:
        print("❌ OPENROUTER_API_KEY not found, skipping OpenRouter test")
        return
    
    try:
        llm_client = LLMClient(openrouter_key, provider="openrouter")
        
        response = await llm_client.achat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "Say hello in a creative way!"}],
            temperature=0.8
        )
        
        content = response.choices[0].message.content
        print(f"✅ OpenRouter Response: {content}")
        
    except Exception as e:
        print(f"❌ OpenRouter call failed: {e}")


async def main():
    """Main demo function."""
    await demo_async_llm()
    await demo_openrouter_async()
    
    print("\n🎉 Demo completed!")
    print("\nKey benefits of async LLM calls:")
    print("• Non-blocking: Other operations can run while waiting for LLM responses")
    print("• Better performance: Can handle multiple requests concurrently")
    print("• Improved responsiveness: Discord bot won't freeze during LLM calls")
    print("• Resource efficiency: No need for thread pool executors")


if __name__ == "__main__":
    asyncio.run(main())
