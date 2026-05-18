from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.db.models import Student


def _set_dotted(d: dict, dotted_key: str, value):
    parts = dotted_key.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


class GetStudentProfileTool(BaseTool):
    name = "get_student_profile"
    description = "Fetch the student's profile (name, grade, school, target_school, stream, profile_json)."
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self) -> dict:
        sess = self._session_factory()
        s = sess.get(Student, self._student_id)
        if s is None:
            return {}
        return {
            "id": s.id, "name": s.name, "grade": s.grade,
            "school": s.school, "target_school": s.target_school,
            "stream": s.stream, "profile_json": dict(s.profile_json or {}),
        }


class UpdateStudentProfileTool(BaseTool):
    name = "update_student_profile"
    description = (
        "Update student profile fields. Keys without dots write to top-level fields; "
        "keys with dots write into profile_json (e.g. 'profile_json.bedtime')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "updates": {
                "type": "object",
                "description": "field-name -> value mapping",
            },
        },
        "required": ["updates"],
    }
    is_readonly = False

    _TOP_LEVEL = {"name", "grade", "school", "target_school", "stream"}

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, updates: dict) -> dict:
        sess = self._session_factory()
        s = sess.get(Student, self._student_id)
        if s is None:
            return {"status": "not_found"}
        pj = dict(s.profile_json or {})
        for k, v in updates.items():
            if k in self._TOP_LEVEL:
                setattr(s, k, v)
            elif k.startswith("profile_json."):
                _set_dotted(pj, k[len("profile_json."):], v)
            else:
                _set_dotted(pj, k, v)
        s.profile_json = pj
        sess.commit()
        return {"updated_fields": list(updates.keys())}
