"""Test token counting functionality."""

import pytest
from llm.clients import LLMClient
from bot.conversation import ConversationStore, MAX_CONVERSATION_TOKENS


class TestTokenCounting:
    """Test token counting and conversation trimming."""

    def test_token_counting_basic(self):
        """Test basic token counting functionality."""
        client = LLMClient("dummy-key", provider="openai")
        messages = [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you for asking!"}
        ]
        
        token_count = client.count_tokens(messages)
        assert token_count > 0
        assert isinstance(token_count, int)

    def test_token_counting_with_tool_calls(self):
        """Test token counting with tool calls."""
        client = LLMClient("dummy-key", provider="openai")
        messages = [
            {"role": "user", "content": "Find me a movie"},
            {
                "role": "assistant", 
                "content": "I'll search for movies for you.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "search_movies",
                            "arguments": '{"query": "action movies", "limit": 5}'
                        }
                    }
                ]
            }
        ]
        
        token_count = client.count_tokens(messages)
        assert token_count > 0

    def test_conversation_store_token_trimming(self):
        """Test that conversations are trimmed when they exceed token limits."""
        client = LLMClient("dummy-key", provider="openai")
        store = ConversationStore(client)
        
        # Add a very long message that would exceed token limits
        long_content = "This is a very long message. " * 10000  # Create a very long message
        conv_id = 123
        
        # Add the long message
        store.add_user(conv_id, long_content)
        
        # Check that the conversation was trimmed
        messages = store.tail(conv_id)
        token_count = store.get_token_count(conv_id)
        
        # Should be under the limit
        assert token_count <= MAX_CONVERSATION_TOKENS
        
        # Should have at least one message for context
        assert len(messages) >= 1

    def test_conversation_store_no_llm_client(self):
        """Test conversation store works without LLM client."""
        store = ConversationStore()
        conv_id = 123
        
        # Should work without errors
        store.add_user(conv_id, "Hello")
        store.add_assistant(conv_id, "Hi there!")
        
        messages = store.tail(conv_id)
        assert len(messages) == 2
        
        # Token count should be 0 without client
        token_count = store.get_token_count(conv_id)
        assert token_count == 0

    def test_conversation_store_set_llm_client(self):
        """Test setting LLM client after initialization."""
        store = ConversationStore()
        client = LLMClient("dummy-key", provider="openai")
        
        conv_id = 123
        store.add_user(conv_id, "Hello")
        
        # Set client and check token counting works
        store.set_llm_client(client)
        token_count = store.get_token_count(conv_id)
        assert token_count > 0
