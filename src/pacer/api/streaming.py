"""Shared background-streaming runner.

Used by `POST /message/send` and any other endpoint that needs to push an
assistant reply through the orchestrator and into the SSE event bus
(e.g. `POST /errors/{id}/start-review`).
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

# Single-process registry of cancellable streaming tasks.
# Shared with `/message/{message_id}/stop`. Multi-worker deploys would need
# this moved to a DB flag the loop polls per tick.
_streaming_tasks: dict[int, asyncio.Task] = {}


def get_streaming_tasks() -> dict[int, asyncio.Task]:
    """Accessor so callers (notably the stop endpoint) share one dict."""
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
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={
                    "session_id": session_id,
                    "message_id": assistant_message_id,
                    "agent": "homeroom",
                },
            ))

            async def on_delta(text: str) -> None:
                if not text:
                    return
                collected.append(text)
                local_store.append_content_to_message(assistant_message_id, text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": assistant_message_id, "delta": text},
                ))

            out = await orch.handle_streaming(
                user_message_for_llm, history=history, on_delta=on_delta,
            )
            local_store.finalize_message(
                assistant_message_id, content=out.final_text, status="done",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id,
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
                assistant_message_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id, "agent": "homeroom",
                    "stop_reason": "user_stopped",
                },
            ))
        except Exception:
            log.exception("streaming failed message_id=%s", assistant_message_id)
            local_store.finalize_message(
                assistant_message_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id, "agent": "homeroom",
                    "stop_reason": "error",
                },
            ))
        finally:
            db_session.close()
            _streaming_tasks.pop(assistant_message_id, None)

    task = asyncio.create_task(run())
    _streaming_tasks[assistant_message_id] = task
    return task


def _should_summarize(store: SessionStore, session_id: int, interval: int) -> bool:
    if interval <= 1:
        return True
    msgs = store.list_messages(session_id)
    assistant_count = sum(1 for m in msgs if m.role == "assistant" and m.status == "done")
    return assistant_count > 0 and assistant_count % interval == 0
