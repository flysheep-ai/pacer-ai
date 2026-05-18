from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import SearchMemoryTool
from pacer.tools.skill_tools import LoadSkillTool, ListSkillsTool
from pacer.tools.delegate_tools import ReturnToHomeroomTool
from pacer.tools.vision_tool import VisionUnderstandImageTool
from pacer.tools.error_tools import SaveErrorRecordTool, GenerateVariantTool, MarkErrorReviewedTool
from pacer.tools.mastery_tools import UpdateStudentMasteryTool, GetStudentWeaknessTool
from pacer.skills.loader import SkillsLoader

SUBJECT_SYSTEM_TMPL = """你是一位{subject}学科老师，专业、严谨、爱启发。不寒暄、不闲聊，专注讲解。

工作流程：
1. 先调 list_skills(subject="{subject}") 看可用的知识点资料
2. 调 load_skill(name=...) 加载相关知识点的完整内容
3. 给学生分步讲解，关键提示要点。如果学生提供了图片，用 vision_understand_image 先看题
4. 如果学生答错了，用 save_error_record 记录
5. 讲解后问"要不要做变式题？"→ 用 generate_variant 出题 → 用 mark_error_reviewed 反馈
6. 讲完后调 return_to_homeroom 把对话交回班主任
学生当前的薄弱点你可以用 get_student_weakness 和 search_memory(query="...") 查询。"""


def build_subject_teacher_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    subject: str, skills_loader: SkillsLoader, vision_model: str,
    max_iterations: int = 8,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(SearchMemoryTool(session_factory, student_id))
    reg.register(LoadSkillTool(loader=skills_loader))
    reg.register(ListSkillsTool(loader=skills_loader))
    reg.register(VisionUnderstandImageTool(llm=llm, model=vision_model))
    reg.register(SaveErrorRecordTool(session_factory, student_id))
    reg.register(GenerateVariantTool(llm=llm))
    reg.register(MarkErrorReviewedTool(session_factory, student_id))
    reg.register(UpdateStudentMasteryTool(session_factory, student_id))
    reg.register(GetStudentWeaknessTool(session_factory, student_id))
    reg.register(ReturnToHomeroomTool())
    return AgentLoop(
        llm=llm, tools=reg,
        system_prompt=SUBJECT_SYSTEM_TMPL.format(subject=subject),
        max_iterations=max_iterations,
    )
