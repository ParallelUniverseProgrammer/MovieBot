import asyncio
from types import SimpleNamespace
from pathlib import Path
import json
import pytest

from bot.agent import Agent


class DummyLLM:
    def __init__(self, scripted):
        self.scripted = scripted
        self.calls = []

    def chat(self, *, model, messages, tools=None, tool_choice=None, temperature=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        # Pop next scripted response
        resp = self.scripted.pop(0)
        return resp


def mk_choice(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def mk_tool_call(name, args):
    fn = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(id="tc1", type="function", function=fn)


@pytest.mark.asyncio
async def test_invalid_json_args_triggers_error_and_finalization(tmp_path: Path, monkeypatch):
    # First model response requests a tool with invalid JSON args
    first = mk_choice(content="", tool_calls=[mk_tool_call("read_household_preferences", "{invalid json}")])
    # Second response (finalization) returns normal text
    second = mk_choice(content="Final answer", tool_calls=None)

    # Scripted LLM
    dummy_llm = DummyLLM([first, second])

    # Patch Agent to use dummy LLM and minimal tools
    from bot.tools.registry import build_openai_tools_and_registry

    def fake_build(project_root, llm):
        tools, reg = build_openai_tools_and_registry(project_root, llm)
        return tools, reg

    monkeypatch.setattr("bot.agent.LLMClient", lambda api_key: dummy_llm)

    agent = Agent(api_key="x", project_root=tmp_path)
    # Provide minimal base messages
    resp = agent.converse([{"role": "user", "content": "hi"}])

    # Ensure finalization returned the second response
    assert getattr(resp, "choices", None) and getattr(resp.choices[0].message, "content", None) == "Final answer"
    # Ensure there were two LLM calls
    assert len(dummy_llm.calls) == 2


@pytest.mark.asyncio
async def test_tool_timeout_leads_to_finalization(tmp_path: Path, monkeypatch):
    # First model response requests a tool with valid args
    first = mk_choice(content="", tool_calls=[mk_tool_call("read_household_preferences", json.dumps({}))])
    # Second response after tool result is a final text
    second = mk_choice(content="All good", tool_calls=None)

    dummy_llm = DummyLLM([first, second])
    monkeypatch.setattr("bot.agent.LLMClient", lambda api_key: dummy_llm)

    # Force very small timeout via config
    cfg = tmp_path / "config" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("llm:\n  maxIters: 2\ntools:\n  timeoutMs: 1\n")

    # Patch tool impl to sleep beyond timeout by intercepting make_read_household_preferences
    from bot.tools import tool_impl

    async def slow_impl(args: dict) -> dict:
        await asyncio.sleep(0.01)
        return {"ok": True}

    monkeypatch.setattr(tool_impl, "make_read_household_preferences", lambda project_root: (lambda args: slow_impl(args)))

    # Rebuild registry with the patched impl by constructing a new Agent
    agent = Agent(api_key="x", project_root=tmp_path)
    resp = agent.converse([{"role": "user", "content": "ping"}])

    assert getattr(resp.choices[0].message, "content", None) == "All good"
    assert len(dummy_llm.calls) == 2
