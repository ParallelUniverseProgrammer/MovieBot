from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple, Optional
from llm.clients import LLMClient


# Max number of trailing messages (user + assistant) to include in the model context
MAX_HISTORY_MESSAGES: int = 6

# Maximum token limit for conversations (128k tokens)
MAX_CONVERSATION_TOKENS: int = 128_000


class ConversationStore:
    """In-memory conversation history keyed by a conversation id.

    Conversation id can be the Discord channel id to share context across a channel
    or a tuple of (channel_id, user_id) for per-user threads. We default to channel id
    to keep things household-oriented.
    
    Includes safety net to prevent conversations from exceeding maximum token limits.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._store: Dict[int, Deque[Dict[str, str]]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY_MESSAGES))
        self._llm_client = llm_client

    def _trim_conversation_if_needed(self, conv_id: int) -> None:
        """Trim conversation if it exceeds the maximum token limit.
        
        Removes oldest messages first while preserving the most recent context.
        """
        if not self._llm_client:
            return
            
        messages = list(self._store[conv_id])
        if not messages:
            return
            
        # Count tokens in current conversation
        token_count = self._llm_client.count_tokens(messages)
        
        # If under limit, no trimming needed
        if token_count <= MAX_CONVERSATION_TOKENS:
            return
            
        # Remove oldest messages until under limit
        while token_count > MAX_CONVERSATION_TOKENS and len(messages) > 1:
            # Remove oldest message (keep at least one for context)
            removed_message = messages.pop(0)
            # Recalculate token count
            token_count = self._llm_client.count_tokens(messages)
            
        # Update the store with trimmed conversation
        self._store[conv_id] = deque(messages, maxlen=MAX_HISTORY_MESSAGES)

    def add_user(self, conv_id: int, content: str) -> None:
        self._store[conv_id].append({"role": "user", "content": content})
        self._trim_conversation_if_needed(conv_id)

    def add_assistant(self, conv_id: int, content: str | None) -> None:
        """Append an assistant message if it is non-empty.

        Skips appending when the model timed out or returned None/empty, to avoid
        corrupting the chat history with null messages.
        """
        if content is None:
            return
        # Normalize and skip empty/whitespace-only messages, too
        if isinstance(content, str) and content.strip() == "":
            return
        self._store[conv_id].append({"role": "assistant", "content": content})
        self._trim_conversation_if_needed(conv_id)

    def tail(self, conv_id: int) -> List[Dict[str, str]]:
        return list(self._store[conv_id])

    def reset(self, conv_id: int) -> None:
        self._store.pop(conv_id, None)

    def get_token_count(self, conv_id: int) -> int:
        """Get the current token count for a conversation."""
        if not self._llm_client:
            return 0
        return self._llm_client.count_tokens(list(self._store[conv_id]))

    def set_llm_client(self, llm_client: LLMClient) -> None:
        """Set the LLM client for token counting."""
        self._llm_client = llm_client


CONVERSATIONS = ConversationStore()


