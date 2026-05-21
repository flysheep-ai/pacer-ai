from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from pacer.api.deps import get_db, current_student_id
from pacer.db.models import ErrorRecord, Plan, StudentMastery, KnowledgePoint

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
            "point_name": kp.point_name if kp else "?",
            "mastery_score": m.mastery_score,
            "correct_count": m.correct_count,
            "wrong_count": m.wrong_count,
        })
    return result
