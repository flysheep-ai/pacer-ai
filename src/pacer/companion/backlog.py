from __future__ import annotations
from sqlalchemy.orm import Session
from pacer.db.models import PendingEvent
from pacer.session.events import SSEEvent


async def enqueue_or_publish(state, student_id: int, event_type: str, text: str):
    bus = state.event_bus
    data = {"text": text, "event_type": event_type}
    if bus.has_subscriber(student_id):
        await bus.publish(SSEEvent(student_id=student_id, event_type=event_type, data=data))
    else:
        db = state._db_factory() if hasattr(state, '_db_factory') else None
        if db:
            pe = PendingEvent(student_id=student_id, event_type=event_type, data_json=data)
            db.add(pe); db.commit()


def flush_backlog(db: Session, bus, student_id: int):
    rows = db.query(PendingEvent).filter_by(student_id=student_id).order_by(PendingEvent.created_at).all()
    for row in rows:
        import asyncio
        try:
            asyncio.create_task(bus.publish(SSEEvent(
                student_id=student_id, event_type=row.event_type, data=row.data_json,
            )))
        except RuntimeError:
            pass
        db.delete(row)
    db.commit()
