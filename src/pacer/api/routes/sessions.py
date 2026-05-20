from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pacer.api.deps import get_db, current_student_id
from pacer.db.models import ChatSession, Message

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _derive_title(first_user_msg: Message | None) -> str:
    if first_user_msg is None:
        return "新对话"
    raw = first_user_msg.content or ""
    # Image messages are stored as JSON {"text":..., "image_base64":...}; pull text only.
    if raw.startswith("{") and "image_base64" in raw:
        try:
            data = json.loads(raw)
            text = (data.get("text") or "").strip()
            if text:
                return text[:24]
            return "[图片]"
        except json.JSONDecodeError:
            pass
    return raw[:24] or "新对话"


class SessionItem(BaseModel):
    id: int
    title: str
    last_msg_at: str | None
    message_count: int


class MessageItem(BaseModel):
    id: int
    role: str
    agent: str | None
    content: str
    status: str | None
    created_at: str | None


class RenameRequest(BaseModel):
    title: str


@router.get("/")
def list_sessions(
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
) -> list[SessionItem]:
    sessions = (
        db.query(ChatSession)
        .filter_by(student_id=student_id, status="active")
        .order_by(desc(ChatSession.last_active_at))
        .all()
    )
    result = []
    for s in sessions:
        msg_count = db.query(Message).filter_by(session_id=s.id).count()
        if s.title:
            title = s.title
        else:
            first_msg = (
                db.query(Message)
                .filter_by(session_id=s.id, role="user")
                .order_by(Message.created_at.asc())
                .first()
            )
            title = _derive_title(first_msg)
        last_active = s.last_active_at.isoformat() if s.last_active_at else None
        result.append(SessionItem(
            id=s.id, title=title, last_msg_at=last_active, message_count=msg_count,
        ))
    return result


@router.get("/{sid}")
def get_session(
    sid: int,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    s = db.query(ChatSession).filter_by(id=sid, student_id=student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    if s.title:
        title = s.title
    else:
        first_msg = (
            db.query(Message)
            .filter_by(session_id=s.id, role="user")
            .order_by(Message.created_at.asc())
            .first()
        )
        title = _derive_title(first_msg)
    return SessionItem(
        id=s.id,
        title=title,
        last_msg_at=s.last_active_at.isoformat() if s.last_active_at else None,
        message_count=db.query(Message).filter_by(session_id=s.id).count(),
    )


@router.get("/{sid}/messages")
def list_messages(
    sid: int,
    limit: int = 100,
    before_id: int | None = None,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
) -> list[MessageItem]:
    s = db.query(ChatSession).filter_by(id=sid, student_id=student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    q = db.query(Message).filter_by(session_id=sid).order_by(Message.created_at.asc())
    if before_id is not None:
        q = q.filter(Message.id < before_id)
    messages = q.limit(limit).all()
    return [
        MessageItem(
            id=m.id, role=m.role, agent=m.agent,
            content=m.content, status=getattr(m, 'status', 'done'),
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in messages
    ]


@router.patch("/{sid}", status_code=204)
def rename_session(
    sid: int,
    req: RenameRequest,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    s = db.query(ChatSession).filter_by(id=sid, student_id=student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    title = (req.title or "").strip()
    if not title or len(title) > 40:
        raise HTTPException(status_code=400, detail="title must be 1-40 characters")
    s.title = title
    db.commit()
    return None


@router.delete("/{sid}", status_code=204)
def delete_session(
    sid: int,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    s = db.query(ChatSession).filter_by(id=sid, student_id=student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    s.status = "archived"
    db.commit()
    return None
