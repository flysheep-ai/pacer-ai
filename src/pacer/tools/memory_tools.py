from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.memory.persistent import PersistentMemory


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "Search the student's long-term memory for entries matching a query."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "keywords to match"},
            "max_results": {"type": "integer", "default": 3},
        },
        "required": ["query"],
    }
    is_readonly = True

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, query: str, max_results: int = 3) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entries = mem.find_relevant(query, max_results=max_results)
        return {"entries": [
            {"type": e.type, "key": e.key, "content": e.content, "importance": e.importance}
            for e in entries
        ]}


class RememberTool(BaseTool):
    name = "remember"
    description = "Persist a fact about the student to long-term memory."
    parameters = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["profile", "weakness", "habit", "goal", "event"]},
            "key": {"type": "string"},
            "content": {"type": "string"},
            "importance": {"type": "number", "default": 0.5},
        },
        "required": ["type", "key", "content"],
    }
    is_readonly = False

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, type: str, key: str, content: str, importance: float = 0.5) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entry = mem.add(type=type, key=key, content=content, importance=importance)
        return {"saved_id": entry.id}
