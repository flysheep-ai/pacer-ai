from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any
import time


@dataclass
class SSEEvent:
    student_id: int
    event_type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, queue_maxsize: int = 100):
        self._subscribers: dict[int, list[asyncio.Queue[SSEEvent]]] = defaultdict(list)
        self._queue_maxsize = queue_maxsize

    def subscribe(self, student_id: int) -> asyncio.Queue[SSEEvent]:
        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers[student_id].append(q)
        return q

    def unsubscribe(self, student_id: int, queue: asyncio.Queue[SSEEvent]) -> None:
        if queue in self._subscribers.get(student_id, []):
            self._subscribers[student_id].remove(queue)

    def has_subscriber(self, student_id: int) -> bool:
        return len(self._subscribers.get(student_id, [])) > 0

    async def publish(self, event: SSEEvent) -> None:
        for q in list(self._subscribers.get(event.student_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(event)
