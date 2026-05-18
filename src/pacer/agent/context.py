from __future__ import annotations
from pacer.llm.client import LLMMessage


def build_messages(
    user_message: str,
    history: list[LLMMessage],
    recalled_memory_block: str | None = None,
) -> list[LLMMessage]:
    msgs = list(history)
    user_text = user_message
    if recalled_memory_block:
        user_text = f"<recalled-memories>\n{recalled_memory_block}\n</recalled-memories>\n\n{user_message}"
    msgs.append(LLMMessage(role="user", content=user_text))
    return msgs
