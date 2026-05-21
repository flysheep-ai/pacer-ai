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

常规答疑流程：
1. 先调 list_skills(subject="{subject}") 看可用的知识点资料
2. 调 load_skill(name=...) 加载相关知识点的完整内容
3. 给学生分步讲解，关键提示要点。如果学生提供了图片，用 vision_understand_image 先看题
4. 如果学生答错了，用 save_error_record 记录
5. 讲解后问"要不要做变式题？"→ 用 generate_variant 出题 → 用 mark_error_reviewed 反馈
6. 讲完后调 return_to_homeroom 把对话交回班主任

【错题复盘协议】
当用户首条消息以 `[复盘错题 #<error_id>]` 开头时，按以下顺序工作：
1. 解析出 error_id、题目、用户答案、正确答案
2. 用 1-2 段把"错在哪 / 正确做法的关键步骤"讲清楚
3. 调 generate_variant(original_stem=...) 出一道变式题，邀请学生作答
4. 收到学生答复后，判断对错：
   - 调 mark_error_reviewed(error_record_id=<error_id>, correct=<bool>)
   - 若该错题关联了 knowledge_point_id，再调 update_student_mastery
5. 简短总结、鼓励，然后 return_to_homeroom

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
    reg.register(SaveErrorRecordTool(session_factory, student_id, llm=llm))
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
