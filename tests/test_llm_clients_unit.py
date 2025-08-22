import pytest
from unittest.mock import Mock, patch, AsyncMock

from llm.clients import LLMClient, OpenRouterClient
import os


def test_openrouter_count_tokens_and_headers_sync_chat():
    client = OpenRouterClient("test-key")
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "tool", "content": "tool output"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "f", "arguments": "{\"a\":1}"}}
            ],
        },
    ]

    # Token counting
    count = client.count_tokens(messages)
    assert isinstance(count, int) and count > 0

    # chat passes extra headers
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        client.chat(model="z-ai/glm-4.5-air:free", messages=[{"role": "user", "content": "hi"}])
        call = mock_create.call_args
        assert "extra_headers" in call.kwargs
        headers = call.kwargs["extra_headers"]
        assert "HTTP-Referer" in headers and "X-Title" in headers


@pytest.mark.asyncio
async def test_openrouter_async_chat_headers():
    client = OpenRouterClient("test-key")
    with patch.object(client.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_acreate:
        mock_acreate.return_value = {"ok": True}
        out = await client.achat(model="z-ai/glm-4.5-air:free", messages=[{"role": "user", "content": "hi"}])
        assert out == {"ok": True}
        call = mock_acreate.call_args
        assert "extra_headers" in call.kwargs


def test_openrouter_headers_use_env_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "MyApp")
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        client.chat(model="z-ai/glm-4.5-air:free", messages=[{"role": "user", "content": "hi"}])
        headers = mock_create.call_args.kwargs["extra_headers"]
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "MyApp"


def test_openrouter_headers_merge_with_caller_provided(monkeypatch):
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://mysite")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "MovieBot")
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            extra_headers={"X-Custom": "1"}
        )
        headers = mock_create.call_args.kwargs["extra_headers"]
        assert headers["HTTP-Referer"] == "https://mysite"
        assert headers["X-Title"] == "MovieBot"
        assert headers["X-Custom"] == "1"


def test_llmclient_openai_sync_chat_reasoning_and_tools():
    c = LLMClient("key", provider="openai")
    with patch.object(c.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
        c.chat(model="gpt-5-mini", messages=[{"role": "user", "content": "hi"}], tools=tools, reasoning="minimal")
        # OpenAI path should include 'reasoning' param; tools should pass through
        args = mock_create.call_args.kwargs
        assert "reasoning" in args and args["reasoning"] == {"effort": "minimal"}
        assert args["tools"] == tools


@pytest.mark.asyncio
async def test_llmclient_openai_async_chat_reasoning_and_tool_choice():
    c = LLMClient("key", provider="openai")
    with patch.object(c.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_acreate:
        mock_acreate.return_value = {"id": "x"}
        out = await c.achat(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": "hi"}],
            tool_choice="required",
            reasoning="high",
        )
        assert out == {"id": "x"}
        args = mock_acreate.call_args.kwargs
        assert "reasoning" in args and args["reasoning"] == {"effort": "high"}
        assert args["tool_choice"] == "required"


def test_llmclient_openrouter_sync_chat_passthrough():
    c = LLMClient("key", provider="openrouter")
    with patch.object(c.client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        c.chat(model="z-ai/glm-4.5-air:free", messages=[{"role": "user", "content": "hi"}], reasoning="medium")
        args = mock_create.call_args.kwargs
        assert args["reasoning"] == {"effort": "medium"}
        assert "extra_headers" in args


@pytest.mark.asyncio
async def test_llmclient_openrouter_async_chat_passthrough():
    c = LLMClient("key", provider="openrouter")
    with patch.object(c.client.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_acreate:
        mock_acreate.return_value = {"ok": True}
        out = await c.achat(model="z-ai/glm-4.5-air:free", messages=[{"role": "user", "content": "hi"}], reasoning="high")
        assert out == {"ok": True}
        args = mock_acreate.call_args.kwargs
        assert args["reasoning"] == {"effort": "high"}
        assert "extra_headers" in args


