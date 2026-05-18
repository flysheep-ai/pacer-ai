from __future__ import annotations
from pacer.tools.base import BaseTool


class DelegateToSubjectTeacherTool(BaseTool):
    name = "delegate_to_subject_teacher"
    description = "Hand the conversation to a subject specialist teacher."
    parameters = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "enum": ["math", "chinese", "english", "physics", "chemistry", "biology"],
            },
            "reason": {"type": "string"},
        },
        "required": ["subject"],
    }
    is_readonly = False

    async def execute(self, *, subject: str, reason: str = "") -> dict:
        return {"delegated_to": "subject_teacher", "subject": subject, "reason": reason}


class DelegateToMoodCompanionTool(BaseTool):
    name = "delegate_to_mood_companion"
    description = "Hand the conversation to the mood companion for emotional support."
    parameters = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": [],
    }
    is_readonly = False

    async def execute(self, *, reason: str = "") -> dict:
        return {"delegated_to": "mood_companion", "reason": reason}


class ReturnToHomeroomTool(BaseTool):
    name = "return_to_homeroom"
    description = "Signal that this agent has completed its task and control should return to the homeroom teacher."
    parameters = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": [],
    }
    is_readonly = False

    async def execute(self, *, summary: str = "") -> dict:
        return {"return": True, "summary": summary}


class LogMoodTool(BaseTool):
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

    def __init__(self, session_factory, student_id):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, self_score: int, summary: str,
                      topics: list[str] | None = None, red_flag: bool = False) -> dict:
        from pacer.db.models import MoodLog
        sess = self._session_factory()
        log = MoodLog(
            student_id=self._student_id, self_score=self_score,
            topics=topics or [], summary=summary, red_flag=red_flag,
        )
        sess.add(log); sess.commit(); sess.refresh(log)
        return {"id": log.id, "red_flag": red_flag}
