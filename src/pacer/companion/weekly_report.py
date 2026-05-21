"""Weekly report: aggregate 7 days of plans, errors, mood, and mastery."""
from __future__ import annotations
from datetime import date, timedelta

from sqlalchemy.orm import Session

from pacer.agents.homeroom import build_homeroom_agent
from pacer.db.models import ErrorRecord, MoodLog, Plan, StudentMastery


async def generate_weekly_report(db: Session, state, student_id: int) -> str:
    today = date.today()
    week_start = today - timedelta(days=7)

    # Plan completion
    plans = (
        db.query(Plan)
        .filter(
            Plan.student_id == student_id,
            Plan.type == "daily",
            Plan.date >= week_start,
        )
        .all()
    )
    plan_done = 0
    plan_total = 0
    for p in plans:
        tasks = p.tasks_json or []
        plan_total += len(tasks)
        plan_done += sum(1 for t in tasks if isinstance(t, dict) and t.get("done"))

    # Errors
    errors = (
        db.query(ErrorRecord)
        .filter(
            ErrorRecord.student_id == student_id,
            ErrorRecord.created_at >= week_start,
        )
        .all()
    )
    error_count = len(errors)
    reviewed_count = sum(1 for e in errors if e.review_count > 0)

    # Mood trend
    moods = (
        db.query(MoodLog)
        .filter(
            MoodLog.student_id == student_id,
            MoodLog.created_at >= week_start,
        )
        .order_by(MoodLog.created_at.asc())
        .all()
    )
    mood_scores = [m.self_score for m in moods if m.self_score is not None]
    mood_trend = "无数据"
    if len(mood_scores) >= 2:
        if mood_scores[-1] > mood_scores[0]:
            mood_trend = "上升 ↑"
        elif mood_scores[-1] < mood_scores[0]:
            mood_trend = "下降 ↓"
        else:
            mood_trend = "平稳 →"
    elif mood_scores:
        mood_trend = f"均分 {sum(mood_scores) / len(mood_scores):.1f}/5"

    # Mastery changes
    mastery_items = (
        db.query(StudentMastery)
        .filter(
            StudentMastery.student_id == student_id,
            StudentMastery.last_practice_at >= week_start,
        )
        .all()
    )
    improved = [m for m in mastery_items if m.mastery_score >= 0.7]
    struggling = [m for m in mastery_items if m.mastery_score < 0.4]

    prompt = (
        f"[SYSTEM TASK · weekly report] 以下是学生本周（{week_start} ~ {today}）数据：\n"
        f"- 计划完成：{plan_done}/{plan_total}"
        f"（{plan_total > 0 and round(plan_done / plan_total * 100) or 0}%）\n"
        f"- 新增错题：{error_count}，已复盘 {reviewed_count}\n"
        f"- 心情趋势：{mood_trend}\n"
        f"- 掌握较好（≥70%）：{len(improved)} 个知识点\n"
        f"- 需要加强（<40%）：{len(struggling)} 个知识点\n\n"
        f"请用 5-8 句话写一份温暖的周报，包含：\n"
        f"1. 本周计划完成情况\n"
        f"2. 错题回顾（主要错误类型）\n"
        f"3. 心态观察\n"
        f"4. 下周学习建议（聚焦薄弱点）\n"
        f"风格：鼓励但不敷衍，具体但不啰嗦。"
    )
    agent = build_homeroom_agent(
        llm=state.llm, session_factory=lambda: db, student_id=student_id,
    )
    result = await agent.run(prompt, history=[])
    return result.final_text
