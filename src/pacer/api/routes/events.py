from __future__ import annotations
import asyncio
import json
from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse
from pacer.api.deps import optional_student_id

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    token: str | None = Query(None),
    student_id: int = Depends(optional_student_id),
):
    bus = request.app.state.event_bus
    queue = bus.subscribe(student_id)

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": evt.event_type,
                        "data": json.dumps(evt.data, ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            bus.unsubscribe(student_id, queue)

    return EventSourceResponse(event_gen())
