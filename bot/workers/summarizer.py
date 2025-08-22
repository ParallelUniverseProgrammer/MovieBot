from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm.clients import LLMClient
from config.loader import resolve_llm_selection


class SummarizerWorker:
    def __init__(self, api_key: str, provider: str = "openai") -> None:
        self.llm = LLMClient(api_key, provider=provider)

    async def summarize_json(self, project_root, obj: Any, *, schema_hint: Optional[str] = None, target_chars: int = 400) -> str:
        provider, sel = resolve_llm_selection(project_root, "summarizer")
        model = sel.get("model", "gpt-5-nano")
        system = {
            "role": "system",
            "content": (
                "You compress JSON/tool outputs into a compact English summary under the requested character limit. "
                "Keep identifiers, counts, and the most relevant fields. No bullet points."
            ),
        }
        user = {
            "role": "user",
            "content": (
                f"Schema hint: {schema_hint or '-'}\nMax chars: {target_chars}\n\nData:\n" + str(obj)
            )[:4000],
        }
        resp = await self.llm.achat(model=model, messages=[system, user], **(sel.get("params", {}) or {}))
        content = getattr(getattr(resp, "choices", [{}])[0], "message", {}).get("content", "")
        if isinstance(content, str) and len(content) > target_chars:
            return content[: target_chars - 1] + "…"
        return content or ""


