from __future__ import annotations
import json
import re
from pacer.llm.client import LLMClient, LLMMessage
from pacer.memory.persistent import PersistentMemory

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

示例：
[{"type":"goal","key":"目标大学","content":"学生目标是清华大学计算机系"},
 {"type":"weakness","key":"导数计算","content":"学生在复合函数求导时容易出错，需要多练链式法则"}]
"""


async def extract_and_store(
    llm: LLMClient,
    student_id: int,
    user_text: str,
    assistant_text: str,
    session_factory,
) -> int:
    """Extract key facts from an exchange and store as memory entries.

    Returns the number of new memories stored.
    """
    if not assistant_text or len(assistant_text) < 20:
        return 0

    messages = [
        LLMMessage(role="user", content=f"用户: {user_text[:500]}\n助手: {assistant_text[:1000]}\n\n请提取值得记住的事实。"),
    ]

    try:
        resp = await llm.chat(
            messages,
            system=_SUMMARIZE_SYSTEM,
            model=llm.model,
        )

        # Parse JSON from response (may be wrapped in markdown)
        text = resp.text.strip()
        # Remove markdown code fences if present
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

        facts = json.loads(text)
        if not isinstance(facts, list):
            return 0

        session = session_factory()
        mem = PersistentMemory(session, student_id)
        count = 0
        for f in facts:
            if not isinstance(f, dict):
                continue
            t = f.get("type", "event")
            k = f.get("key", "")
            c = f.get("content", "")
            if not k or not c:
                continue
            # Skip if very similar entry already exists
            existing = mem.find_by_key_and_type(k, t)
            if existing:
                continue
            mem.add(type=t, key=k, content=c, importance=0.6)
            count += 1
        return count
    except (json.JSONDecodeError, Exception):
        return 0
