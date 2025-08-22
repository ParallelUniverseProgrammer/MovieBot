import os
import pytest

from bot.tools.registry import build_openai_tools_and_registry
from llm.clients import LLMClient


@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_accepts_tool_schema(tmp_path):
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    llm = LLMClient(os.environ["OPENAI_API_KEY"], provider="openai")
    openai_tools, _ = build_openai_tools_and_registry(tmp_path, llm)
    # Minimal ping with tools attached; model shouldn't error on tool schema
    resp = await llm.achat(model="gpt-5-mini", messages=[{"role": "user", "content": "hi"}], tools=openai_tools)
    assert resp is not None
