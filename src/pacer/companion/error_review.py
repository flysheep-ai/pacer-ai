from __future__ import annotations
from datetime import date
from sqlalchemy.orm import Session
from pacer.db.models import ErrorRecord
from pacer.agents.homeroom import build_homeroom_agent


async def run_error_review(db: Session, state, student_id: int) -> str:
    today_errors = db.query(ErrorRecord).filter(
        ErrorRecord.student_id == student_id,
        ErrorRecord.created_at >= date.today(),
    ).count()
    if today_errors == 0:
        return "今天没有新错题，很棒！要复习一下昨天的吗？"
    prompt = f"[SYSTEM TASK · error review] 学生今天积累了 {today_errors} 道错题。请用 get_recent_errors 查看，然后逐一简要回顾，询问是否要深入讲解某一道。"
    agent = build_homeroom_agent(llm=state.llm, session_factory=lambda: db, student_id=student_id)
    result = await agent.run(prompt, history=[])
    return result.final_text
