import asyncio
import pytest
from pacer.session.events import EventBus, SSEEvent


@pytest.mark.asyncio
async def test_subscribe_receives_published_event():
    bus = EventBus()
    sub = bus.subscribe(student_id=1)
    await bus.publish(SSEEvent(student_id=1, event_type="message", data={"text": "hi"}))
    evt = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert evt.event_type == "message"
    assert evt.data == {"text": "hi"}


@pytest.mark.asyncio
async def test_subscribers_are_isolated_by_student():
    bus = EventBus()
    sub_a = bus.subscribe(student_id=1)
    sub_b = bus.subscribe(student_id=2)
    await bus.publish(SSEEvent(student_id=1, event_type="msg", data={}))
    await bus.publish(SSEEvent(student_id=2, event_type="other", data={}))
    a_evt = await asyncio.wait_for(sub_a.get(), timeout=1.0)
    b_evt = await asyncio.wait_for(sub_b.get(), timeout=1.0)
    assert a_evt.event_type == "msg"
    assert b_evt.event_type == "other"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    sub = bus.subscribe(student_id=1)
    bus.unsubscribe(student_id=1, queue=sub)
    await bus.publish(SSEEvent(student_id=1, event_type="x", data={}))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.get(), timeout=0.1)
