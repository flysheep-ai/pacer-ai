from __future__ import annotations
from datetime import date
from sqlalchemy.orm import Session
from pacer.db.models import Plan, ErrorRecord
from pacer.agents.homeroom import build_homeroom_agent


async def generate_daily_report(db: Session, state, student_id: int) -> str:
    today = date.today()
    plan = db.query(Plan).filter_by(
        student_id=student_id, type="daily",
    ).filter(Plan.date >= today).order_by(Plan.id.desc()).first()
    completion = "无" if plan is None else _completion_str(plan.tasks_json)
    error_count = db.query(ErrorRecord).filter(
        ErrorRecord.student_id == student_id,
        ErrorRecord.created_at >= today,
    ).count()
    reviewed = db.query(ErrorRecord).filter(
        ErrorRecord.student_id == student_id,
        ErrorRecord.created_at >= today,
        ErrorRecord.review_count > 0,
    ).count()
    prompt = (
        f"[SYSTEM TASK · daily report] 今日学习日报：\n"
        f"- 计划完成：{completion}\n"
        f"- 新增错题：{error_count}\n"
        f"- 已复盘：{reviewed}\n"
        f"请用 3-5 句话总结今日，鼓励学生，并提醒明日重点。"
    )
    agent = build_homeroom_agent(llm=state.llm, session_factory=lambda: db, student_id=student_id)
    result = await agent.run(prompt, history=[])
    return result.final_text


def _completion_str(tasks: list[dict]) -> str:
    if not tasks: return "未制定"
    done = sum(1 for t in tasks if t.get("done"))
    return f"{done}/{len(tasks)}"
