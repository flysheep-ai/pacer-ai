from __future__ import annotations
from datetime import datetime, timezone
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.db.models import StudentMastery


class UpdateStudentMasteryTool(BaseTool):
    name = "update_student_mastery"
    description = "Update the student's mastery score for a knowledge point."
    parameters = {
        "type": "object",
        "properties": {
            "knowledge_point_id": {"type": "integer"},
            "correct": {"type": "boolean"},
        },
        "required": ["knowledge_point_id", "correct"],
    }
    is_readonly = False

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, knowledge_point_id: int, correct: bool) -> dict:
        sess = self._session_factory()
        sm = sess.query(StudentMastery).filter_by(
            student_id=self._student_id, knowledge_point_id=knowledge_point_id,
        ).first()
        if sm is None:
            sm = StudentMastery(
                student_id=self._student_id, knowledge_point_id=knowledge_point_id,
            )
            sess.add(sm)
        if correct:
            sm.correct_count += 1
        else:
            sm.wrong_count += 1
        total = sm.correct_count + sm.wrong_count
        sm.mastery_score = sm.correct_count / total if total > 0 else 0.0
        sm.last_practice_at = datetime.now(timezone.utc)
        sess.commit(); sess.refresh(sm)
        return {"knowledge_point_id": knowledge_point_id, "mastery_score": sm.mastery_score}


class GetStudentWeaknessTool(BaseTool):
    name = "get_student_weakness"
    description = "Get the student's weakest knowledge points."
    parameters = {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "top_n": {"type": "integer", "default": 5},
        },
    }
    is_readonly = True

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, subject: str | None = None, top_n: int = 5) -> dict:
        sess = self._session_factory()
        q = sess.query(StudentMastery).filter_by(student_id=self._student_id)
        if subject:
            from pacer.db.models import KnowledgePoint
            q = q.join(KnowledgePoint).filter(KnowledgePoint.subject == subject)
        rows = q.order_by(StudentMastery.mastery_score.asc()).limit(top_n).all()
        return {"weaknesses": [
            {"knowledge_point_id": sm.knowledge_point_id,
             "mastery_score": sm.mastery_score,
             "correct_count": sm.correct_count, "wrong_count": sm.wrong_count}
            for sm in rows
        ]}
