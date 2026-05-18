from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy.orm import Session
from pacer.agents.homeroom import build_homeroom_agent
from pacer.db.models import Plan, ErrorRecord

_PROMPT_TMPL = """[SYSTEM TASK · morning briefing] 现在是早上 07:00。
学生数据：
- 昨日计划完成情况：{yesterday_status}
- 待复习错题数：{review_count}

请：
1. 用一句温暖的早安开头
2. 用 create_plan 生成今日 3-5 个任务（明确学科 + 时间块）
3. 输出简洁的今日重点摘要
"""


async def generate_morning_plan(db: Session, state, student_id: int) -> str:
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday_plan = (
        db.query(Plan)
        .filter_by(student_id=student_id, type="daily")
        .filter(Plan.date >= yesterday)
        .order_by(Plan.id.desc()).first()
    )
    yesterday_status = "无" if yesterday_plan is None else _summarize(yesterday_plan.tasks_json)
    review_count = db.query(ErrorRecord).filter(
        ErrorRecord.student_id == student_id, ErrorRecord.mastery_level < 0.7,
    ).count()
    prompt = _PROMPT_TMPL.format(yesterday_status=yesterday_status, review_count=review_count)
    agent = build_homeroom_agent(
        llm=state.llm, session_factory=lambda: db, student_id=student_id,
    )
    result = await agent.run(prompt, history=[])
    return result.final_text


def _summarize(tasks: list[dict]) -> str:
    if not tasks: return "未制定"
    done = sum(1 for t in tasks if t.get("done"))
    return f"{done}/{len(tasks)} 完成"
