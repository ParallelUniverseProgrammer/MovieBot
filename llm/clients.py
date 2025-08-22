from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
import os

from openai import AsyncOpenAI, OpenAI
try:
    from openai import BadRequestError  # type: ignore
except Exception:  # pragma: no cover
    BadRequestError = Exception  # fallback if SDK changes
import tiktoken


@dataclass
class LLMConfig:
    api_key: str
    provider: str = "openai"  # "openai" or "openrouter"
    base_url: Optional[str] = None


class OpenRouterClient:
    """OpenRouter client that provides OpenAI-compatible API interface."""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        # Initialize async client for async operations
        self.async_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        # Initialize tiktoken for token counting
        self._encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4/5 family encoding

        # Default OpenRouter tracking headers (optional but recommended by OpenRouter docs)
        referer = os.getenv("OPENROUTER_SITE_URL") or "https://github.com/your-repo/moviebot"
        app_title = os.getenv("OPENROUTER_APP_NAME") or "MovieBot"
        self._default_headers: Dict[str, str] = {
            "HTTP-Referer": referer,
            "X-Title": app_title,
        }

    def count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count the total number of tokens in a conversation.
        
        Uses OpenAI's tiktoken library for accurate token counting.
        """
        total_tokens = 0
        for message in messages:
            # Count tokens in content
            if message.get("content"):
                total_tokens += len(self._encoding.encode(message["content"]))
            
            # Count tokens in tool calls if present
            if message.get("tool_calls"):
                for tool_call in message["tool_calls"]:
                    if tool_call.get("function", {}).get("arguments"):
                        total_tokens += len(self._encoding.encode(tool_call["function"]["arguments"]))
                    if tool_call.get("function", {}).get("name"):
                        total_tokens += len(self._encoding.encode(tool_call["function"]["name"]))
            
            # Count tokens in tool results if present
            if message.get("role") == "tool" and message.get("content"):
                total_tokens += len(self._encoding.encode(message["content"]))
        
        return total_tokens

    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameter names for Chat Completions compatibility.

        - If any alternate token keys are provided, convert the first one to
          max_tokens when max_tokens is not already present.
        - Always remove alternate keys to avoid sending duplicate/conflicting params.
        """
        out = dict(params)
        for k in ("max_response_tokens", "max_output_tokens", "max_completion_tokens"):
            if k in out:
                if "max_tokens" not in out:
                    out["max_tokens"] = out[k]
                # remove the alternate key regardless to prevent duplicates
                out.pop(k, None)
        return out

    def chat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"model": model, "messages": messages}
        if tools is not None:
            params["tools"] = tools
        # Reasoning param (top-level per SDK expectations)
        if reasoning is not None:
            params["reasoning"] = {"effort": reasoning}
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        # Normalize any provided kwargs
        kwargs = self._normalize_params(kwargs)
        # Add OpenRouter-specific headers for tracking (merge env-driven defaults with any caller-provided headers)
        provided_headers = kwargs.pop("extra_headers", None)
        extra_headers = dict(self._default_headers)
        if isinstance(provided_headers, dict):
            extra_headers.update(provided_headers)
        params["extra_headers"] = extra_headers
        params.update(kwargs)
        
        return self.client.chat.completions.create(**params)  # type: ignore[no-any-return]

    async def achat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Async version of chat method."""
        params: Dict[str, Any] = {"model": model, "messages": messages}
        if tools is not None:
            params["tools"] = tools
        if reasoning is not None:
            params["reasoning"] = {"effort": reasoning}
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        # Normalize any provided kwargs
        kwargs = self._normalize_params(kwargs)
        # Add OpenRouter-specific headers for tracking (merge env-driven defaults with any caller-provided headers)
        provided_headers = kwargs.pop("extra_headers", None)
        extra_headers = dict(self._default_headers)
        if isinstance(provided_headers, dict):
            extra_headers.update(provided_headers)
        params["extra_headers"] = extra_headers
        params.update(kwargs)
        
        return await self.async_client.chat.completions.create(**params)  # type: ignore[no-any-return]


class LLMClient:
    def __init__(self, api_key: str, provider: str = "openai"):
        self.provider = provider
        if provider == "openrouter":
            self.client = OpenRouterClient(api_key)
        else:
            self.client = OpenAI(api_key=api_key)
            # Initialize async client for async operations
            self.async_client = AsyncOpenAI(api_key=api_key)
        # Initialize tiktoken for token counting
        self._encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4/5 family encoding

    def count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count the total number of tokens in a conversation.
        
        Uses OpenAI's tiktoken library for accurate token counting.
        """
        total_tokens = 0
        for message in messages:
            # Count tokens in content
            if message.get("content"):
                total_tokens += len(self._encoding.encode(message["content"]))
            
            # Count tokens in tool calls if present
            if message.get("tool_calls"):
                for tool_call in message["tool_calls"]:
                    if tool_call.get("function", {}).get("arguments"):
                        total_tokens += len(self._encoding.encode(tool_call["function"]["arguments"]))
                    if tool_call.get("function", {}).get("name"):
                        total_tokens += len(self._encoding.encode(tool_call["function"]["name"]))
            
            # Count tokens in tool results if present
            if message.get("role") == "tool" and message.get("content"):
                total_tokens += len(self._encoding.encode(message["content"]))
        
        return total_tokens

    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parameter names for Chat Completions compatibility.

        See OpenRouterClient._normalize_params for behavior; we mirror it here.
        """
        out = dict(params)
        for k in ("max_response_tokens", "max_output_tokens", "max_completion_tokens"):
            if k in out:
                if "max_tokens" not in out:
                    out["max_tokens"] = out[k]
                out.pop(k, None)
        return out

    def _normalize_params_openai(self, model: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize params for OpenAI Chat Completions.

        - For GPT-5 and o1/o3 family models, prefer 'max_completion_tokens'.
        - Accept alternates and coerce appropriately.
        """
        out = dict(params)
        model_lower = (model or "").lower()
        prefers_completion = model_lower.startswith("gpt-5") or model_lower.startswith("o1") or model_lower.startswith("o3")
        # Collect candidate values
        alt_keys = ("max_response_tokens", "max_output_tokens", "max_completion_tokens")
        alt_val = None
        for k in alt_keys:
            if k in out and alt_val is None:
                alt_val = out[k]
            # remove all alt keys regardless
            if k in out:
                out.pop(k, None)
        # If model prefers completion tokens
        if prefers_completion:
            if "max_tokens" in out:
                out["max_completion_tokens"] = out.pop("max_tokens")
            elif alt_val is not None:
                out["max_completion_tokens"] = alt_val
            # else leave as-is
        else:
            # Older models: keep max_tokens if present; if only alt provided, convert to max_tokens
            if "max_tokens" not in out and alt_val is not None:
                out["max_tokens"] = alt_val
        return out

    def chat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        # Do not force reasoning; rely on selection providers
        # For OpenRouter, we need to handle the model name differently
        if self.provider == "openrouter":
            # If using OpenRouter, ensure the model name is in the correct format
            # The model should already be in the correct format (e.g., "z-ai/glm-4.5-air:free")
            return self.client.chat(
                model=model,
                messages=messages,
                tools=tools,
                reasoning=reasoning,
                tool_choice=tool_choice,
                **self._normalize_params(kwargs)
            )
        else:
            # OpenAI client
            params: Dict[str, Any] = {"model": model, "messages": messages}
            if tools is not None:
                params["tools"] = tools
            # Forward reasoning for supported models using reasoning_effort (no mapping)
            if reasoning is not None:
                params["reasoning_effort"] = str(reasoning)
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
            params.update(self._normalize_params_openai(model, kwargs))
            return self.client.chat.completions.create(**params)  # type: ignore[no-any-return]

    async def achat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Async version of chat method."""
        # Do not force reasoning; rely on selection providers
        # For OpenRouter, we need to handle the model name differently
        if self.provider == "openrouter":
            # If using OpenRouter, ensure the model name is in the correct format
            # The model should already be in the correct format (e.g., "z-ai/glm-4.5-air:free")
            return await self.client.achat(
                model=model,
                messages=messages,
                tools=tools,
                reasoning=reasoning,
                tool_choice=tool_choice,
                **self._normalize_params(kwargs)
            )
        else:
            # OpenAI async client
            params: Dict[str, Any] = {"model": model, "messages": messages}
            if tools is not None:
                params["tools"] = tools
            # Forward reasoning for supported models using reasoning_effort (no mapping)
            if reasoning is not None:
                params["reasoning_effort"] = str(reasoning)
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
            params.update(self._normalize_params_openai(model, kwargs))
            return await self.async_client.chat.completions.create(**params)  # type: ignore[no-any-return]


