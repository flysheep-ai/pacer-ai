from __future__ import annotations
from pacer.tools.base import BaseTool, StudentScopedTool
from pacer.db.models import MoodLog


class ReturnToHomeroomTool(BaseTool):
    """Marker tool the subject/mood agents call to indicate task completion.

    Doesn't actually switch agents (orchestration is router-based, not
    delegation-based) — the call shows up in the trace so the calling
    sub-agent's end-of-turn intent is auditable.
    """

    name = "return_to_homeroom"
    description = "Signal that this agent has completed its task."
    parameters = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": [],
    }
    is_readonly = False

    async def execute(self, *, summary: str = "") -> dict:
        return {"return": True, "summary": summary}


class LogMoodTool(StudentScopedTool):
    name = "log_mood"
    description = "Persist a mood log entry for the student."
    parameters = {
        "type": "object",
        "properties": {
            "self_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "topics": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "red_flag": {"type": "boolean", "default": False},
        },
        "required": ["self_score", "summary"],
    }
    is_readonly = False

    async def execute(self, *, self_score: int, summary: str,
                      topics: list[str] | None = None, red_flag: bool = False) -> dict:
        sess = self._session_factory()
        log = MoodLog(
            student_id=self._student_id, self_score=self_score,
            topics=topics or [], summary=summary, red_flag=red_flag,
        )
        sess.add(log); sess.commit(); sess.refresh(log)
        return {"id": log.id, "red_flag": red_flag}
