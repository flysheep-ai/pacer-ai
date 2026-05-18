from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import SearchMemoryTool
from pacer.tools.delegate_tools import LogMoodTool, ReturnToHomeroomTool

MOOD_SYSTEM = """你是一位温柔、不评判的心态陪伴者，像一位心理咨询取向的学姐/学长。
不解题、不催进度，只关注学生的感受。

工作风格：
- 用具体的倾听 + 共情技术，不说"加油""一切都会好的"这类敷衍
- 必要时引导呼吸 / 认知重构 / 情境再框架
- 对话结束前调 log_mood 记录（self_score 1-5，topics 列表，summary 一句话）
- 如果学生表达自伤/严重抑郁/极端念头：red_flag=true，并立即给出兜底信息
  包含专业热线号码（全国心理援助热线 400-161-9995）
- 完成对话后调 return_to_homeroom"""


def build_mood_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    max_iterations: int = 6,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(SearchMemoryTool(session_factory, student_id))
    reg.register(LogMoodTool(session_factory, student_id))
    reg.register(ReturnToHomeroomTool())
    return AgentLoop(
        llm=llm, tools=reg, system_prompt=MOOD_SYSTEM,
        max_iterations=max_iterations,
    )
