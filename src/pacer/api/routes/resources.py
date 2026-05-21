from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from pacer.api.deps import get_db, current_student_id
from pacer.api.streaming import start_assistant_stream
from pacer.db.models import ErrorRecord, Plan, StudentMastery, KnowledgePoint
from pacer.session.store import SessionStore

router = APIRouter(tags=["resources"])


@router.get("/errors")
def list_errors(
    subject: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    q = db.query(ErrorRecord).filter_by(student_id=student_id)
    if subject:
        q = q.join(ErrorRecord.question).filter_by(subject=subject)
    total = q.count()
    items = q.order_by(ErrorRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": e.id, "error_type": e.error_type, "source": e.source,
                "user_answer": e.user_answer, "correct_answer": e.correct_answer,
                "explanation_text": e.explanation_text, "review_count": e.review_count,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/errors/{eid}")
def get_error(eid: int, db: Session = Depends(get_db), student_id: int = Depends(current_student_id)):
    e = db.query(ErrorRecord).filter_by(id=eid, student_id=student_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": e.id, "error_type": e.error_type, "user_answer": e.user_answer,
        "correct_answer": e.correct_answer, "explanation_text": e.explanation_text,
    }


@router.get("/plans")
def list_plans(
    type: str | None = Query(None),
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    q = db.query(Plan).filter_by(student_id=student_id)
    if type:
        q = q.filter_by(type=type)
    items = q.order_by(Plan.date.desc()).all()
    return {
        "items": [
            {
                "id": p.id, "type": p.type, "tasks": p.tasks_json,
                "feedback": p.feedback,
                "date": p.date.isoformat() if p.date else None,
            }
            for p in items
        ]
    }


@router.get("/plans/{pid}")
def get_plan(pid: int, db: Session = Depends(get_db), student_id: int = Depends(current_student_id)):
    p = db.query(Plan).filter_by(id=pid, student_id=student_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return {"id": p.id, "type": p.type, "tasks": p.tasks_json, "feedback": p.feedback}


class TaskUpdateRequest(BaseModel):
    done: bool


@router.patch("/plans/{plan_id}/tasks/{task_id}", status_code=204)
def patch_plan_task(
    plan_id: int,
    task_id: str,
    req: TaskUpdateRequest,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    p = db.query(Plan).filter_by(id=plan_id, student_id=student_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="plan not found")
    tasks = list(p.tasks_json or [])
    found = False
    for t in tasks:
        if isinstance(t, dict) and t.get("id") == task_id:
            t["done"] = req.done
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="task not found")
    p.tasks_json = tasks
    flag_modified(p, "tasks_json")
    db.commit()
    return None


@router.get("/mastery")
def get_mastery(db: Session = Depends(get_db), student_id: int = Depends(current_student_id)):
    items = db.query(StudentMastery).filter_by(student_id=student_id).all()
    result: dict[str, list[dict]] = {}
    for m in items:
        kp = db.query(KnowledgePoint).filter_by(id=m.knowledge_point_id).first()
        subject = kp.subject if kp else "未知"
        result.setdefault(subject, []).append({
            "knowledge_point_id": m.knowledge_point_id,
            "point_name": kp.point_name if kp else "?",
            "mastery_score": m.mastery_score,
            "correct_count": m.correct_count,
            "wrong_count": m.wrong_count,
        })
    return result


@router.post("/errors/{error_id}/start-review", status_code=202)
async def start_error_review(
    error_id: int,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    e = db.query(ErrorRecord).filter_by(id=error_id, student_id=student_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="error not found")
    stem = e.question.stem if e.question else "(题干缺失)"
    seed_text = (
        f"[复盘错题 #{e.id}] "
        f"题目: {stem}\n"
        f"我的答案: {e.user_answer or '(空)'}\n"
        f"正确答案: {e.correct_answer or '(未给)'}"
    )

    store = SessionStore(db)
    chat = store.create_session(student_id=student_id)
    store.append_message(
        chat.id, role="user", agent=None, content=seed_text,
        metadata={"error_review_id": e.id},
    )
    assistant_msg = store.create_empty_assistant(chat.id, agent="subject_teacher")

    start_assistant_stream(
        app_state=request.app.state,
        student_id=student_id,
        session_id=chat.id,
        assistant_message_id=assistant_msg.id,
        user_message_for_llm=seed_text,
        user_text_for_memory=seed_text,
        history=[],
    )
    return {"session_id": chat.id, "assistant_message_id": assistant_msg.id}


class MasteryStartReviewRequest(BaseModel):
    knowledge_point_id: int


@router.post("/mastery/start-review", status_code=202)
async def start_mastery_review(
    req: MasteryStartReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    kp = db.get(KnowledgePoint, req.knowledge_point_id)
    if kp is None:
        raise HTTPException(status_code=404, detail="knowledge point not found")

    seed_text = (
        f"[复习知识点 #{kp.id}] {kp.subject} · {kp.point_name}\n"
        f"请帮我讲解这个知识点，并出几道练习题。"
    )

    store = SessionStore(db)
    chat = store.create_session(student_id=student_id)
    store.append_message(
        chat.id, role="user", agent=None, content=seed_text,
        metadata={"knowledge_point_id": kp.id},
    )
    assistant_msg = store.create_empty_assistant(chat.id, agent="subject_teacher")

    start_assistant_stream(
        app_state=request.app.state,
        student_id=student_id,
        session_id=chat.id,
        assistant_message_id=assistant_msg.id,
        user_message_for_llm=seed_text,
        user_text_for_memory=seed_text,
        history=[],
    )
    return {"session_id": chat.id, "assistant_message_id": assistant_msg.id}
