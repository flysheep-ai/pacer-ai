"""Shared background-streaming runner.

Used by `POST /message/send` and any other endpoint that needs to push an
assistant reply through the orchestrator and into the SSE event bus
(e.g. `POST /errors/{id}/start-review`).

Cancellation works at two levels:
1. In-process: asyncio.Task.cancel() via the `_streaming_tasks` dict.
   Fast, works within a single worker.
2. Cross-worker: a `streaming_cancellation` DB row per message_id.
   The stop endpoint sets `cancel_requested=True`; the stream loop polls
   every `CANCEL_POLL_INTERVAL` deltas. Enables multi-worker deploys.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from pacer.api import deps
from pacer.config import get_settings
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.session.events import SSEEvent
from pacer.session.store import SessionStore

log = logging.getLogger("pacer.streaming")

# How many deltas between DB cancellation checks (keep low enough that
# the user doesn't wait long, high enough that we don't hammer the DB).
CANCEL_POLL_INTERVAL = 10

_streaming_tasks: dict[int, asyncio.Task] = {}


def get_streaming_tasks() -> dict[int, asyncio.Task]:
    return _streaming_tasks


def start_assistant_stream(
    *,
    app_state: Any,
    student_id: int,
    session_id: int,
    assistant_message_id: int,
    user_message_for_llm: str | list[dict[str, Any]],
    user_text_for_memory: str,
    history: list[LLMMessage],
) -> asyncio.Task:
    """Spawn the streaming background task.

    Caller MUST have already:
    - persisted the user message into the session
    - created an empty placeholder assistant message (`status='streaming'`)
    - built `history` (excluding the trailing user message)
    """
    settings = get_settings()
    bus = app_state.event_bus
    msg_id = assistant_message_id

    # Write a cancellation row so cross-worker stops can reach this stream.
    _init_cancellation(msg_id)

    async def run() -> None:
        collected: list[str] = []
        db_session = deps._SessionLocal()
        local_store = SessionStore(db_session)
        bg_factory = lambda: db_session
        orch = Orchestrator(
            llm=app_state.llm,
            router_model=settings.router_model,
            session_factory=bg_factory,
            student_id=student_id,
            skills_loader=app_state.skills_loader,
        )
        delta_count = 0
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={
                    "session_id": session_id,
                    "message_id": msg_id,
                    "agent": "homeroom",
                },
            ))

            async def on_delta(text: str) -> None:
                nonlocal delta_count
                if not text:
                    return
                collected.append(text)
                local_store.append_content_to_message(msg_id, text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": msg_id, "delta": text},
                ))
                delta_count += 1
                if delta_count % CANCEL_POLL_INTERVAL == 0 and _is_cancelled(msg_id, db_session):
                    raise asyncio.CancelledError("cancelled via DB flag")

            out = await orch.handle_streaming(
                user_message_for_llm, history=history, on_delta=on_delta,
            )
            local_store.finalize_message(
                msg_id, content=out.final_text, status="done",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": msg_id,
                    "agent": out.agent_used,
                    "stop_reason": "completed",
                },
            ))

            try:
                from pacer.db.models import LLMUsage
                db_session.add(LLMUsage(
                    student_id=student_id, session_id=session_id,
                    agent=out.agent_used, model=app_state.llm.model,
                    input_tokens=out.inner.total_input_tokens,
                    output_tokens=out.inner.total_output_tokens,
                    iterations=out.inner.iterations,
                ))
                db_session.commit()
            except Exception:
                log.exception("failed to write LLMUsage")

            try:
                if _should_summarize(local_store, session_id, settings.memory_summarize_interval):
                    from pacer.memory.summarizer import extract_and_store
                    n = await extract_and_store(
                        app_state.llm, student_id, user_text_for_memory, out.final_text,
                        lambda: deps._SessionLocal(),
                        model=settings.router_model,
                    )
                    if n > 0:
                        log.info("stored %d new memories student=%s", n, student_id)
            except Exception:
                log.exception("memory summarizer failed")
        except asyncio.CancelledError:
            local_store.finalize_message(
                msg_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": msg_id, "agent": "homeroom",
                    "stop_reason": "user_stopped",
                },
            ))
        except Exception:
            log.exception("streaming failed message_id=%s", msg_id)
            local_store.finalize_message(
                msg_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": msg_id, "agent": "homeroom",
                    "stop_reason": "error",
                },
            ))
        finally:
            db_session.close()
            _streaming_tasks.pop(msg_id, None)
            _delete_cancellation(msg_id)

    task = asyncio.create_task(run())
    _streaming_tasks[msg_id] = task
    return task


def request_cancellation(message_id: int) -> None:
    """Set the DB cancellation flag so any worker running this stream exits.

    Callers (notably the stop endpoint) should call this AND also
    cancel the in-memory task if available.
    """
    db = deps._SessionLocal()
    try:
        from pacer.db.models import StreamingCancellation
        row = db.get(StreamingCancellation, message_id)
        if row is not None:
            row.cancel_requested = True
            db.commit()
        else:
            db.add(StreamingCancellation(message_id=message_id, cancel_requested=True))
            db.commit()
    except Exception:
        log.exception("failed to request cancellation for message %s", message_id)
    finally:
        db.close()


# -- internal helpers ---------------------------------------------------------

def _init_cancellation(message_id: int) -> None:
    db = deps._SessionLocal()
    try:
        from pacer.db.models import StreamingCancellation
        db.merge(StreamingCancellation(message_id=message_id, cancel_requested=False))
        db.commit()
    except Exception:
        log.debug("failed to init cancellation row for message %s", message_id)
    finally:
        db.close()


def _is_cancelled(message_id: int, db_session) -> bool:
    try:
        from pacer.db.models import StreamingCancellation
        row = db_session.get(StreamingCancellation, message_id)
        return row is not None and row.cancel_requested
    except Exception:
        return False


def _delete_cancellation(message_id: int) -> None:
    db = deps._SessionLocal()
    try:
        from pacer.db.models import StreamingCancellation
        row = db.get(StreamingCancellation, message_id)
        if row is not None:
            db.delete(row)
            db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _should_summarize(store: SessionStore, session_id: int, interval: int) -> bool:
    if interval <= 1:
        return True
    msgs = store.list_messages(session_id)
    assistant_count = sum(1 for m in msgs if m.role == "assistant" and m.status == "done")
    return assistant_count > 0 and assistant_count % interval == 0
