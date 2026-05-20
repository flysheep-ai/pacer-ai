from __future__ import annotations
import json
import logging
import re
from collections.abc import Callable

from sqlalchemy.orm import Session

from pacer.llm.client import LLMClient, LLMMessage
from pacer.memory.persistent import PersistentMemory

log = logging.getLogger("pacer.summarizer")

_SUMMARIZE_SYSTEM = """你是一个记忆提取助手。从对话中提取关于学生的重要事实，每条事实单独列出。

只提取对以后对话有用的信息，例如：
- 学生的个人目标、偏好、习惯
- 学生的薄弱知识点、常见错误
- 学生的重要经历、状态变化
- 学生明确表达的喜欢/不喜欢

不要提取：
- 临时的、一次性的对话内容（如"今天作业写完了"）
- 纯知识点讲解（如"导数的定义是..."）
- 泛泛的鼓励或问候

输出严格的 JSON 数组，每个元素包含：
- "type": "profile"|"weakness"|"habit"|"goal"|"event"
- "key": 简短标签（10字以内）
- "content": 完整描述（50字以内）

如果没有值得记住的信息，输出空数组 []。
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text


async def extract_and_store(
    llm: LLMClient,
    student_id: int,
    user_text: str,
    assistant_text: str,
    session_factory: Callable[[], Session],
    *,
    model: str | None = None,
) -> int:
    """Extract key facts from one exchange and store as memory entries.

    Returns the number of *new* (non-duplicate) memories stored.
    `model` lets callers route this to a cheaper model (e.g. Haiku) instead of
    the main one used for replies.
    """
    if not assistant_text or len(assistant_text) < 20:
        return 0

    prompt = (
        f"用户: {user_text[:500]}\n助手: {assistant_text[:1000]}\n\n请提取值得记住的事实。"
    )
    try:
        resp = await llm.chat(
            [LLMMessage(role="user", content=prompt)],
            system=_SUMMARIZE_SYSTEM, model=model,
        )
    except Exception:
        log.exception("summarizer LLM call failed student=%s", student_id)
        return 0

    text = _strip_code_fences(resp.text)
    try:
        facts = json.loads(text)
    except json.JSONDecodeError:
        log.warning("summarizer non-JSON output student=%s text=%r", student_id, text[:200])
        return 0
    if not isinstance(facts, list):
        log.warning("summarizer non-list output student=%s", student_id)
        return 0

    session = session_factory()
    try:
        mem = PersistentMemory(session, student_id)
        count = 0
        for f in facts:
            if not isinstance(f, dict):
                continue
            t = (f.get("type") or "event").strip()
            k = (f.get("key") or "").strip()
            c = (f.get("content") or "").strip()
            if not k or not c:
                continue
            entry, reason = mem.add_if_novel(type=t, key=k, content=c, importance=0.6)
            if entry is not None:
                count += 1
            elif reason == "duplicate_semantic":
                log.debug("skipping near-duplicate memory key=%s", k)
        return count
    finally:
        # Only close if the factory gave us a session we own.
        try:
            session.close()
        except Exception:
            pass
