import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from bot.workers.summarizer import SummarizerWorker


@pytest.mark.asyncio
async def test_summarizer_worker_bounds_and_schema(tmp_path):
    worker = SummarizerWorker(api_key="dummy", provider="openai")

    fake_resp = type("R", (), {"choices": [type("C", (), {"message": {"content": "summary text"}})]})()

    with patch.object(worker.llm, "achat", new_callable=AsyncMock) as mock_achat:
        mock_achat.return_value = fake_resp
        out = await worker.summarize_json(tmp_path, {"items": [1, 2, 3]}, schema_hint="list of ints", target_chars=20)
        assert isinstance(out, str)
        assert len(out) <= 20
