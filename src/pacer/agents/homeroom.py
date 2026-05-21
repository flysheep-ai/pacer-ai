from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool
from pacer.tools.plan_tools import GetTodayPlanTool, UpdatePlanTool, CreatePlanTool
from pacer.tools.error_tools import GetRecentErrorsTool
from pacer.tools.mastery_tools import GetStudentWeaknessTool

HOMEROOM_SYSTEM = """你是一位温和、专业的高三 AI 班主任。你了解这个学生，关心他的学习节奏与情绪状态。

你的职责：
- 接住所有对话开端，识别学生意图
- 计划生成 / 进度督促 / 日报 / 晚安
- 学科问题与情绪话题会由系统自动转交给学科老师/心态师；你专注于综合性的引导
- 自然地补充学生画像（用 remember 工具记录值得长期记住的事实），不要审问
- 简洁、温暖、不啰嗦
- 用学生使用的语言回答（学生说中文就用中文，说英文就用英文）

上下文中可能出现 <recalled-memories> 块——那是关于该学生的长期记忆，可作为参考但不要照搬复述。"""


def build_homeroom_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    max_iterations: int = 5,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(RememberTool(session_factory, student_id))
    reg.register(GetStudentProfileTool(session_factory, student_id))
    reg.register(UpdateStudentProfileTool(session_factory, student_id))
    reg.register(GetTodayPlanTool(session_factory, student_id))
    reg.register(UpdatePlanTool(session_factory, student_id))
    reg.register(CreatePlanTool(session_factory, student_id))
    reg.register(GetRecentErrorsTool(session_factory, student_id))
    reg.register(GetStudentWeaknessTool(session_factory, student_id))
    return AgentLoop(
        llm=llm, tools=reg, system_prompt=HOMEROOM_SYSTEM,
        max_iterations=max_iterations,
    )
