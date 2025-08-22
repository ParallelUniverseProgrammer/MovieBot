from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI, OpenAI
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

    def chat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"model": model, "messages": messages}
        if tools is not None:
            params["tools"] = tools
        if reasoning is not None:
            params["reasoning"] = {"effort": reasoning}
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        
        # Add OpenRouter-specific headers for tracking
        extra_headers = {
            "HTTP-Referer": "https://github.com/your-repo/moviebot",  # Optional: for rankings
            "X-Title": "MovieBot",  # Optional: for rankings
        }
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
        
        # Add OpenRouter-specific headers for tracking
        extra_headers = {
            "HTTP-Referer": "https://github.com/your-repo/moviebot",  # Optional: for rankings
            "X-Title": "MovieBot",  # Optional: for rankings
        }
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

    def chat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        # Force minimal reasoning for gpt-5-mini unless overridden
        if model == "gpt-5-mini" and (reasoning is None or reasoning == ""):
            reasoning = "minimal"
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
                **kwargs
            )
        else:
            # OpenAI client
            params: Dict[str, Any] = {"model": model, "messages": messages}
            if tools is not None:
                params["tools"] = tools
            if reasoning is not None:
                params["reasoning"] = {"effort": reasoning}
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
            params.update(kwargs)
            return self.client.chat.completions.create(**params)  # type: ignore[no-any-return]

    async def achat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """Async version of chat method."""
        # Force minimal reasoning for gpt-5-mini unless overridden
        if model == "gpt-5-mini" and (reasoning is None or reasoning == ""):
            reasoning = "minimal"
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
                **kwargs
            )
        else:
            # OpenAI async client
            params: Dict[str, Any] = {"model": model, "messages": messages}
            if tools is not None:
                params["tools"] = tools
            if reasoning is not None:
                params["reasoning"] = {"effort": reasoning}
            if tool_choice is not None:
                params["tool_choice"] = tool_choice
            params.update(kwargs)
            return await self.async_client.chat.completions.create(**params)  # type: ignore[no-any-return]


