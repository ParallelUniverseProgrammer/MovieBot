"""Tests for OpenRouter integration."""

import pytest
from unittest.mock import Mock, patch
from llm.clients import LLMClient, OpenRouterClient


def test_openrouter_client_initialization():
    """Test that OpenRouterClient initializes correctly."""
    client = OpenRouterClient("test-api-key")
    assert str(client.client.base_url).rstrip('/') == "https://openrouter.ai/api/v1"
    assert hasattr(client, '_encoding')


def test_llm_client_openrouter_provider():
    """Test that LLMClient correctly initializes with OpenRouter provider."""
    client = LLMClient("test-api-key", provider="openrouter")
    assert client.provider == "openrouter"
    assert isinstance(client.client, OpenRouterClient)


def test_llm_client_openai_provider():
    """Test that LLMClient correctly initializes with OpenAI provider."""
    client = LLMClient("test-api-key", provider="openai")
    assert client.provider == "openai"
    assert hasattr(client.client, 'chat')


def test_llm_client_default_provider():
    """Test that LLMClient defaults to OpenAI provider."""
    client = LLMClient("test-api-key")
    assert client.provider == "openai"


def test_openrouter_chat_with_headers():
    """Test that OpenRouter chat includes proper headers."""
    client = OpenRouterClient("test-api-key")
    
    with patch.object(client.client.chat.completions, 'create') as mock_create:
        mock_create.return_value = Mock()
        
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        # Verify the call was made with extra_headers
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert "extra_headers" in call_args[1]
        headers = call_args[1]["extra_headers"]
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers


def test_token_counting_consistency():
    """Test that token counting works the same for both providers."""
    openai_client = LLMClient("test-key", provider="openai")
    openrouter_client = LLMClient("test-key", provider="openrouter")
    
    messages = [{"role": "user", "content": "Hello world"}]
    
    openai_count = openai_client.count_tokens(messages)
    openrouter_count = openrouter_client.count_tokens(messages)
    
    # Both should return the same token count for the same input
    assert openai_count == openrouter_count
    assert openai_count > 0
