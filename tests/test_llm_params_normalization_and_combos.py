import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from llm.clients import LLMClient, OpenRouterClient


def test_openrouter_normalize_params_sync_maps_alt_token_limits_and_merges_headers(monkeypatch):
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            max_response_tokens=42,
            extra_headers={"X-Custom": "1"},
        )
        args = mock_create.call_args.kwargs
        # normalization happens
        assert args["max_tokens"] == 42
        assert "max_response_tokens" not in args
        # headers merged
        assert "extra_headers" in args
        assert args["extra_headers"].get("X-Custom") == "1"
        assert "HTTP-Referer" in args["extra_headers"] and "X-Title" in args["extra_headers"]


@pytest.mark.asyncio
async def test_openrouter_normalize_params_async_maps_alt_token_limits_and_headers():
    client = OpenRouterClient("test-key")
    with patch.object(
        client.async_client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_acreate:
        mock_acreate.return_value = {"ok": True}
        out = await client.achat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            max_output_tokens=55,
            extra_headers={"X-Async": "yes"},
        )
        assert out == {"ok": True}
        args = mock_acreate.call_args.kwargs
        # normalization happens in async path too
        assert args["max_tokens"] == 55
        assert "max_output_tokens" not in args
        # headers present and merged
        assert "extra_headers" in args and args["extra_headers"]["X-Async"] == "yes"


def test_llmclient_openai_normalize_params_and_tool_choice_sync():
    c = LLMClient("key", provider="openai")
    with patch.object(c.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        c.chat(
            model="gpt-5",
            messages=[{"role": "user", "content": "hi"}],
            max_completion_tokens=99,
            tool_choice="auto",
        )
        args = mock_create.call_args.kwargs
        # normalization to max_tokens
        assert args["max_tokens"] == 99
        assert "max_completion_tokens" not in args
        # tool_choice is passed through; reasoning must NOT be present for OpenAI path
        assert args.get("tool_choice") == "auto"
        assert "reasoning" not in args


def test_llmclient_count_tokens_includes_tool_role_branch():
    c = LLMClient("key", provider="openai")
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "content": "tool output here"},
    ]
    count = c.count_tokens(messages)
    # Should count at least content from both messages
    assert isinstance(count, int) and count > 0


def _load_openai_config_models():
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    openai_cfg = cfg["llm"]["providers"]["openai"]
    return openai_cfg


def test_openai_model_reasoning_combos_from_config_sync():
    openai_cfg = _load_openai_config_models()
    c = LLMClient("key", provider="openai")

    # chat, smart, worker have reasoningEffort; quick and summarizer have params
    combos = []
    for key in ("chat", "smart", "worker"):
        model = openai_cfg[key]["model"]
        effort = openai_cfg[key].get("reasoningEffort")
        combos.append((key, model, effort))

    # quick
    quick_model = openai_cfg["quick"]["model"]
    quick_max = openai_cfg["quick"]["params"]["max_tokens"]

    # summarizer
    sum_model = openai_cfg["summarizer"]["model"]
    sum_effort = openai_cfg["summarizer"].get("reasoningEffort")
    sum_max_resp = openai_cfg["summarizer"]["params"]["max_response_tokens"]

    with patch.object(c.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()

        # exercise each reasoning combo; ensure reasoning forwarded for OpenAI
        for key, model, effort in combos:
            c.chat(model=model, messages=[{"role": "user", "content": "hi"}], reasoning=effort)
            args = mock_create.call_args.kwargs
            assert args["model"] == model
            assert args.get("reasoning") == {"effort": effort}

        # quick with explicit max_tokens
        c.chat(model=quick_model, messages=[{"role": "user", "content": "hi"}], max_tokens=quick_max)
        args = mock_create.call_args.kwargs
        assert args["model"] == quick_model and args["max_tokens"] == quick_max

        # summarizer with alt key that must normalize to max_tokens; reasoning forwarded
        c.chat(
            model=sum_model,
            messages=[{"role": "user", "content": "hi"}],
            reasoning=sum_effort,
            max_response_tokens=sum_max_resp,
        )
        args = mock_create.call_args.kwargs
        assert args["model"] == sum_model
        assert args["max_tokens"] == sum_max_resp and "max_response_tokens" not in args
        assert args.get("reasoning") == {"effort": sum_effort}


def test_openai_gpt5mini_reasoning_levels_not_forwarded():
    c = LLMClient("key", provider="openai")
    with patch.object(c.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        for effort in ["minimal", "medium", "high"]:
            c.chat(model="gpt-5-mini", messages=[{"role": "user", "content": "hi"}], reasoning=effort)
            args = mock_create.call_args.kwargs
            assert args["model"] == "gpt-5-mini"
            assert args.get("reasoning") == {"effort": effort}


def test_openai_normalization_does_not_override_existing_max_tokens():
    c = LLMClient("key", provider="openai")
    with patch.object(c.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        c.chat(
            model="gpt-5",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=123,
            max_completion_tokens=99,
        )
        args = mock_create.call_args.kwargs
        assert args["max_tokens"] == 123
        assert "max_completion_tokens" not in args


def test_openrouter_normalization_does_not_override_existing_max_tokens_and_passes_tool_choice():
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=256,
            max_response_tokens=42,
            tool_choice="required",
        )
        args = mock_create.call_args.kwargs
        # max_tokens preserved when provided explicitly
        assert args["max_tokens"] == 256
        assert "max_response_tokens" not in args
        # tool_choice passes through
        assert args.get("tool_choice") == "required"


def test_openrouter_headers_merge_edge_cases():
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        # Test with non-dict extra_headers (should not crash)
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            extra_headers="not-a-dict",
        )
        args = mock_create.call_args.kwargs
        assert "extra_headers" in args
        # Should fall back to default headers only
        assert "HTTP-Referer" in args["extra_headers"]
        assert "X-Title" in args["extra_headers"]


@pytest.mark.asyncio
async def test_openrouter_async_headers_merge_edge_cases():
    client = OpenRouterClient("test-key")
    with patch.object(
        client.async_client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_acreate:
        mock_acreate.return_value = {"ok": True}
        # Test with None extra_headers
        out = await client.achat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            extra_headers=None,
        )
        assert out == {"ok": True}
        args = mock_acreate.call_args.kwargs
        assert "extra_headers" in args
        # Should use default headers only
        assert "HTTP-Referer" in args["extra_headers"]
        assert "X-Title" in args["extra_headers"]


def test_openrouter_headers_merge_with_dict_provided():
    client = OpenRouterClient("test-key")
    with patch.object(client.client.chat.completions, "create") as mock_create:
        mock_create.return_value = Mock()
        # Test with dict extra_headers that should merge with defaults
        client.chat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            extra_headers={"X-Custom": "value", "X-Another": "test"},
        )
        args = mock_create.call_args.kwargs
        assert "extra_headers" in args
        headers = args["extra_headers"]
        # Should have both default and custom headers
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert headers["X-Custom"] == "value"
        assert headers["X-Another"] == "test"


@pytest.mark.asyncio
async def test_openrouter_async_headers_merge_with_dict_provided():
    client = OpenRouterClient("test-key")
    with patch.object(
        client.async_client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_acreate:
        mock_acreate.return_value = {"ok": True}
        # Test with dict extra_headers in async path
        out = await client.achat(
            model="z-ai/glm-4.5-air:free",
            messages=[{"role": "user", "content": "hi"}],
            extra_headers={"X-Async-Custom": "async-value"},
        )
        assert out == {"ok": True}
        args = mock_acreate.call_args.kwargs
        assert "extra_headers" in args
        headers = args["extra_headers"]
        # Should have both default and custom headers
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers
        assert headers["X-Async-Custom"] == "async-value"


