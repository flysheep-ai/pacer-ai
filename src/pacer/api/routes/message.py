from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.config import get_settings

router = APIRouter(prefix="/message", tags=["message"])


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None


class SendAck(BaseModel):
    session_id: int
    assistant_message_id: int


# In-memory registry of cancellable streaming tasks: {message_id: asyncio.Task}
_streaming_tasks: dict[int, asyncio.Task] = {}


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

    # Create a placeholder assistant message (status='streaming')
    msg = store.create_empty_assistant(chat.id, agent="homeroom")
    bus = request.app.state.event_bus

    async def run_stream():
        collected: list[str] = []
        db_session = deps._SessionLocal()
        local_store = SessionStore(db_session)
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={"session_id": chat.id, "message_id": msg.id, "agent": "homeroom"},
            ))

            async def on_delta(text: str):
                collected.append(text)
                # Persist each delta so SSE disconnect doesn't lose content
                local_store.append_content_to_message(msg.id, text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": msg.id, "delta": text},
                ))

            out = await orch.handle_streaming(req.text, history=history, on_delta=on_delta)

            local_store.finalize_message(msg.id, content=out.final_text, status="done")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg.id, "agent": out.agent_used, "stop_reason": "completed"},
            ))
        except asyncio.CancelledError:
            local_store.finalize_message(msg.id, content="".join(collected), status="failed")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg.id, "agent": "homeroom", "stop_reason": "user_stopped"},
            ))
        except Exception:
            import traceback
            traceback.print_exc()
            local_store.finalize_message(msg.id, content="".join(collected), status="failed")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg.id, "agent": "homeroom", "stop_reason": "error"},
            ))
        finally:
            db_session.close()
            _streaming_tasks.pop(msg.id, None)

    task = asyncio.create_task(run_stream())
    _streaming_tasks[msg.id] = task

    return SendAck(session_id=chat.id, assistant_message_id=msg.id)


@router.post("/{message_id}/stop", status_code=204)
async def stop_stream(message_id: int, student_id: int = Depends(deps.current_student_id)):
    task = _streaming_tasks.get(message_id)
    if task is not None and not task.done():
        task.cancel()
    return None
