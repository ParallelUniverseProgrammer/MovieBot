from bot.agent_prompt import AGENT_SYSTEM_PROMPT


def test_minimal_prompt_small_and_no_catalog():
    assert isinstance(AGENT_SYSTEM_PROMPT, str)
    # Updated threshold to accommodate the friendlier, more capable prompt
    assert len(AGENT_SYSTEM_PROMPT) < 3500
    assert "Available tools:" not in AGENT_SYSTEM_PROMPT
