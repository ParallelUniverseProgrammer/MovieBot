from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class LLMConfig:
    api_key: str


class LLMClient:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def chat(self, *, model: str, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, reasoning: Optional[str] = None, tool_choice: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"model": model, "messages": messages}
        if tools is not None:
            params["tools"] = tools
        if reasoning is not None:
            params["reasoning"] = {"effort": reasoning}
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        params.update(kwargs)
        return self.client.chat.completions.create(**params)  # type: ignore[no-any-return]


