from __future__ import annotations
import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pacer.api import deps
from pacer.api.streaming import get_streaming_tasks, start_assistant_stream
from pacer.companion.red_line import (
    ESCALATION_RESPONSE, scan_keywords, should_escalate,
)
from pacer.llm.client import LLMMessage
from pacer.session.store import SessionStore

router = APIRouter(prefix="/message", tags=["message"])
log = logging.getLogger("pacer.message")
_streaming_tasks = get_streaming_tasks()


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None
    image_base64: str | None = None


class SendAck(BaseModel):
    session_id: int
    assistant_message_id: int


@router.post("/send", response_model=SendAck, status_code=202)
async def send_message(
    req: SendRequest,
    request: Request,
    db: Session = Depends(deps.get_db),
    student_id: int = Depends(deps.current_student_id),
) -> SendAck:
    store = SessionStore(db)
    if req.session_id is None:
        chat = store.create_session(student_id=student_id)
    else:
        chat = store.get_session(req.session_id)
        if chat is None or chat.student_id != student_id:
            raise HTTPException(status_code=404, detail="session not found")

    red_hits = scan_keywords(req.text)
    if red_hits and should_escalate(red_hits):
        log.warning(
            "red-line escalation student=%s hits=%s",
            student_id, [h["category"] for h in red_hits],
        )
        store.append_message(chat.id, role="user", agent=None, content=req.text)
        ack_msg = store.append_message(
            chat.id, role="assistant", agent="mood_companion",
            content=ESCALATION_RESPONSE,
            metadata={"red_line": True, "categories": [h["category"] for h in red_hits]},
        )
        try:
            from pacer.db.models import MoodLog
            db.add(MoodLog(
                student_id=student_id, session_id=chat.id, self_score=1,
                topics=[h["category"] for h in red_hits],
                summary="red-line auto-detected", red_flag=True,
            ))
            db.commit()
        except Exception:
            log.exception("failed to write red-line MoodLog")
        return SendAck(session_id=chat.id, assistant_message_id=ack_msg.id)

    if req.image_base64:
        user_content_for_db = json.dumps(
            {"text": req.text, "image_base64": req.image_base64}, ensure_ascii=False,
        )
        user_content_for_llm: str | list[dict[str, Any]] = [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg", "data": req.image_base64,
            }},
            {"type": "text", "text": req.text},
        ]
    else:
        user_content_for_db = req.text
        user_content_for_llm = req.text

    store.append_message(chat.id, role="user", agent=None, content=user_content_for_db)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    msg = store.create_empty_assistant(chat.id, agent="homeroom")

    start_assistant_stream(
        app_state=request.app.state,
        student_id=student_id,
        session_id=chat.id,
        assistant_message_id=msg.id,
        user_message_for_llm=user_content_for_llm,
        user_text_for_memory=req.text,
        history=history,
    )

    return SendAck(session_id=chat.id, assistant_message_id=msg.id)


@router.post("/{message_id}/stop", status_code=204)
async def stop_stream(
    message_id: int,
    student_id: int = Depends(deps.current_student_id),
):
    task = _streaming_tasks.get(message_id)
    if task is not None and not task.done():
        task.cancel()
    return None
