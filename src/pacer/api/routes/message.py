from __future__ import annotations
import asyncio
import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.config import get_settings
from pacer.companion.red_line import scan_keywords, should_escalate, ESCALATION_RESPONSE

router = APIRouter(prefix="/message", tags=["message"])
log = logging.getLogger("pacer.message")


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None
    image_base64: str | None = None


class SendAck(BaseModel):
    session_id: int
    assistant_message_id: int


# In-memory registry of cancellable streaming tasks: {message_id: asyncio.Task}.
# Single-process only — for multi-worker deploys, switch to a DB flag the
# stream loop polls each tick.
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
            raise HTTPException(status_code=404, detail="session not found")

    # Red-line scan on incoming text — short-circuit with crisis resources
    # when keywords are severe enough. Logged + mood entry written.
    red_hits = scan_keywords(req.text)
    if red_hits and should_escalate(red_hits):
        log.warning("red-line escalation student=%s hits=%s", student_id, [h["category"] for h in red_hits])
        store.append_message(chat.id, role="user", agent=None, content=req.text)
        ack_msg = store.append_message(
            chat.id, role="assistant", agent="mood_companion", content=ESCALATION_RESPONSE,
            metadata={"red_line": True, "categories": [h["category"] for h in red_hits]},
        )
        # Best-effort mood log so downstream views can surface the event.
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
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": req.image_base64}},
            {"type": "text", "text": req.text},
        ]
    else:
        user_content_for_db = req.text
        user_content_for_llm = req.text

    store.append_message(chat.id, role="user", agent=None, content=user_content_for_db)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]
    user_message_for_llm: str | list[dict[str, Any]] = (
        user_content_for_llm if req.image_base64 else req.text
    )

    settings = get_settings()

    # Create a placeholder assistant message (status='streaming') *before* the
    # background task starts — caller needs assistant_message_id in the 202 ack.
    msg = store.create_empty_assistant(chat.id, agent="homeroom")
    bus = request.app.state.event_bus
    app_state = request.app.state
    session_id_for_task = chat.id
    msg_id = msg.id

    async def run_stream():
        collected: list[str] = []
        db_session = deps._SessionLocal()
        local_store = SessionStore(db_session)
        # Each background task uses its own DB session via factory; tools that
        # mutate state must call session_factory() fresh per invocation.
        bg_factory = lambda: db_session
        orch = Orchestrator(
            llm=app_state.llm,
            router_model=settings.router_model,
            session_factory=bg_factory,
            student_id=student_id,
            skills_loader=app_state.skills_loader,
        )
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={"session_id": session_id_for_task, "message_id": msg_id, "agent": "homeroom"},
            ))

            async def on_delta(text: str):
                if not text:
                    return
                collected.append(text)
                # Persist each delta so SSE disconnect doesn't lose content.
                local_store.append_content_to_message(msg_id, text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": msg_id, "delta": text},
                ))

            out = await orch.handle_streaming(user_message_for_llm, history=history, on_delta=on_delta)

            local_store.finalize_message(msg_id, content=out.final_text, status="done")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg_id, "agent": out.agent_used, "stop_reason": "completed"},
            ))

            # Telemetry: persist token usage for cost accounting.
            try:
                from pacer.db.models import LLMUsage
                db_session.add(LLMUsage(
                    student_id=student_id, session_id=session_id_for_task,
                    agent=out.agent_used, model=app_state.llm.model,
                    input_tokens=out.inner.total_input_tokens,
                    output_tokens=out.inner.total_output_tokens,
                    iterations=out.inner.iterations,
                ))
                db_session.commit()
            except Exception:
                log.exception("failed to write LLMUsage")

            # Memory summarization is throttled — only every Nth assistant turn.
            try:
                if _should_summarize(local_store, session_id_for_task, settings.memory_summarize_interval):
                    from pacer.memory.summarizer import extract_and_store
                    n = await extract_and_store(
                        app_state.llm, student_id, req.text, out.final_text, lambda: deps._SessionLocal(),
                        model=settings.router_model,
                    )
                    if n > 0:
                        log.info("stored %d new memories student=%s", n, student_id)
            except Exception:
                log.exception("memory summarizer failed")
        except asyncio.CancelledError:
            local_store.finalize_message(msg_id, content="".join(collected), status="failed")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg_id, "agent": "homeroom", "stop_reason": "user_stopped"},
            ))
        except Exception:
            log.exception("streaming failed message_id=%s", msg_id)
            local_store.finalize_message(msg_id, content="".join(collected), status="failed")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg_id, "agent": "homeroom", "stop_reason": "error"},
            ))
        finally:
            db_session.close()
            _streaming_tasks.pop(msg_id, None)

    task = asyncio.create_task(run_stream())
    _streaming_tasks[msg_id] = task

    return SendAck(session_id=chat.id, assistant_message_id=msg_id)


def _should_summarize(store: SessionStore, session_id: int, interval: int) -> bool:
    if interval <= 1:
        return True
    msgs = store.list_messages(session_id)
    assistant_count = sum(1 for m in msgs if m.role == "assistant" and m.status == "done")
    return assistant_count > 0 and assistant_count % interval == 0


@router.post("/{message_id}/stop", status_code=204)
async def stop_stream(message_id: int, student_id: int = Depends(deps.current_student_id)):
    task = _streaming_tasks.get(message_id)
    if task is not None and not task.done():
        task.cancel()
    return None
