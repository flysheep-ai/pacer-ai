from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool, SearchMemoryTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool
from pacer.agent.loop import AgentLoop
from pacer.llm.client import LLMClient, LLMMessage

router = APIRouter(prefix="/message", tags=["message"])

_SYSTEM_PROMPT_MVP = (
    "You are a warm, attentive AI study companion for a Chinese high-school senior. "
    "Speak in simplified Chinese unless the student writes in English. "
    "Use the tools to remember persistent facts and recall context. Be concise."
)


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None


class SendResponse(BaseModel):
    text: str
    session_id: int


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
        assert chat is not None and chat.student_id == student_id

    store.append_message(chat.id, role="user", agent=None, content=req.text)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    reg = ToolRegistry()
    reg.register(RememberTool(lambda: db, student_id))
    reg.register(SearchMemoryTool(lambda: db, student_id))
    reg.register(GetStudentProfileTool(lambda: db, student_id))
    reg.register(UpdateStudentProfileTool(lambda: db, student_id))

    llm: LLMClient = request.app.state.llm
    loop = AgentLoop(llm=llm, tools=reg, system_prompt=_SYSTEM_PROMPT_MVP)
    result = await loop.run(req.text, history=history)

    store.append_message(
        chat.id, role="assistant", agent="homeroom", content=result.final_text,
        metadata={"iterations": result.iterations, "trace": result.trace},
    )
    bus = request.app.state.event_bus
    await bus.publish(SSEEvent(
        student_id=student_id, event_type="assistant_message",
        data={"session_id": chat.id, "text": result.final_text},
    ))
    return SendResponse(text=result.final_text, session_id=chat.id)
