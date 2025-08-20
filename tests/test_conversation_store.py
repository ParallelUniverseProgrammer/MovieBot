import pytest

from bot.conversation import ConversationStore


def test_add_assistant_skips_none():
    cs = ConversationStore()
    conv_id = 1
    cs.add_user(conv_id, "hi")
    cs.add_assistant(conv_id, None)
    tail = cs.tail(conv_id)
    assert len(tail) == 1
    assert tail[0]["role"] == "user"


def test_add_assistant_skips_empty_and_whitespace():
    cs = ConversationStore()
    conv_id = 2
    cs.add_user(conv_id, "hi")
    cs.add_assistant(conv_id, "")
    cs.add_assistant(conv_id, "   \n\t ")
    tail = cs.tail(conv_id)
    assert len(tail) == 1
    assert tail[0]["role"] == "user"


def test_add_assistant_accepts_normal_text():
    cs = ConversationStore()
    conv_id = 3
    cs.add_user(conv_id, "hi")
    cs.add_assistant(conv_id, "hello there")
    tail = cs.tail(conv_id)
    assert len(tail) == 2
    assert tail[1]["role"] == "assistant"
    assert tail[1]["content"] == "hello there"
