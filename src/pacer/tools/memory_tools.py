from __future__ import annotations
from pacer.tools.base import StudentScopedTool
from pacer.memory.persistent import PersistentMemory


class SearchMemoryTool(StudentScopedTool):
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

    async def execute(self, *, query: str, max_results: int = 3) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entries = mem.find_relevant(query, max_results=max_results)
        return {"entries": [
            {"type": e.type, "key": e.key, "content": e.content, "importance": e.importance}
            for e in entries
        ]}


class RememberTool(StudentScopedTool):
    name = "remember"
    description = "Persist a fact about the student to long-term memory (skipped on near-duplicates)."
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

    async def execute(self, *, type: str, key: str, content: str, importance: float = 0.5) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entry, reason = mem.add_if_novel(type=type, key=key, content=content, importance=importance)
        if entry is None:
            return {"saved": False, "reason": reason}
        return {"saved": True, "saved_id": entry.id}
