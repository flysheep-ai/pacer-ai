from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.config import get_settings

router = APIRouter(prefix="/message", tags=["message"])


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None


class SendResponse(BaseModel):
    text: str
    session_id: int
    agent: str


@router.post("/send", response_model=SendResponse)
async def send_message(
    req: SendRequest,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
) -> SendResponse:
    store = SessionStore(db)
    if req.session_id is None:
        chat = store.create_session(student_id=student_id)
    else:
        chat = store.get_session(req.session_id)
        if chat is None or chat.student_id != student_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="session not found")

    store.append_message(chat.id, role="user", agent=None, content=req.text)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    settings = get_settings()
    orch = Orchestrator(
        llm=request.app.state.llm,
        router_model=settings.router_model,
        session_factory=lambda: db,
        student_id=student_id,
        skills_loader=request.app.state.skills_loader,
    )
    out = await orch.handle(req.text, history=history)

    store.append_message(
        chat.id, role="assistant", agent=out.agent_used, content=out.final_text,
        metadata={
            "iterations": out.inner.iterations,
            "trace": out.inner.trace,
            "route": {"intent": out.route.intent, "subject": out.route.subject},
        },
    )
    bus = request.app.state.event_bus
    await bus.publish(SSEEvent(
        student_id=student_id, event_type="assistant_message",
        data={"session_id": chat.id, "text": out.final_text, "agent": out.agent_used},
    ))
    return SendResponse(text=out.final_text, session_id=chat.id, agent=out.agent_used)
