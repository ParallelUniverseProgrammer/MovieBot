from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple


# Max number of trailing messages (user + assistant) to include in the model context
MAX_HISTORY_MESSAGES: int = 12


class ConversationStore:
    """In-memory conversation history keyed by a conversation id.

    Conversation id can be the Discord channel id to share context across a channel
    or a tuple of (channel_id, user_id) for per-user threads. We default to channel id
    to keep things household-oriented.
    """

    def __init__(self) -> None:
        self._store: Dict[int, Deque[Dict[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY_MESSAGES))

    def add_user(self, conv_id: int, content: str) -> None:
        self._store[conv_id].append({"role": "user", "content": content})

    def add_assistant(self, conv_id: int, content: str) -> None:
        self._store[conv_id].append({"role": "assistant", "content": content})

    def tail(self, conv_id: int) -> List[Dict[str, str]]:
        return list(self._store[conv_id])

    def reset(self, conv_id: int) -> None:
        self._store.pop(conv_id, None)


CONVERSATIONS = ConversationStore()


