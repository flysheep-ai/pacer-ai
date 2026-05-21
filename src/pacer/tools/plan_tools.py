from __future__ import annotations
import uuid
from datetime import date, datetime, timezone
from pacer.tools.base import StudentScopedTool
from pacer.db.models import Plan


class GetTodayPlanTool(StudentScopedTool):
    name = "get_today_plan"
    description = "Get the student's plan for today."
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    async def execute(self) -> dict:
        sess = self._session_factory()
        today = date.today()
        plan = sess.query(Plan).filter_by(
            student_id=self._student_id, type="daily",
        ).filter(Plan.date >= today).order_by(Plan.id.desc()).first()
        if plan is None:
            return {"plan": None}
        return {"plan": {
            "id": plan.id, "date": str(plan.date), "tasks": plan.tasks_json,
            "feedback": plan.feedback,
        }}


class CreatePlanTool(StudentScopedTool):
    name = "create_plan"
    description = "Create a new study plan (daily or weekly)."
    parameters = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["daily", "weekly"]},
            "tasks": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["type", "tasks"],
    }
    is_readonly = False

    async def execute(self, *, type: str, tasks: list[dict]) -> dict:
        sess = self._session_factory()
        # Stamp every task with a stable id + explicit done flag so the
        # frontend can toggle individual rows. Caller-supplied id/done win.
        decorated = [
            {**t, "id": t.get("id") or str(uuid.uuid4()), "done": bool(t.get("done", False))}
            for t in tasks
        ]
        plan = Plan(
            student_id=self._student_id, date=datetime.now(timezone.utc),
            type=type, tasks_json=decorated, generated_by="homeroom",
        )
        sess.add(plan); sess.commit(); sess.refresh(plan)
        return {"plan_id": plan.id, "tasks": decorated}


class UpdatePlanTool(StudentScopedTool):
    name = "update_plan"
    description = "Update an existing plan's tasks or feedback."
    parameters = {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer"},
            "tasks_json": {"type": "array", "items": {"type": "object"}},
            "feedback": {"type": "string"},
        },
        "required": ["plan_id"],
    }
    is_readonly = False

    async def execute(self, *, plan_id: int, tasks_json: list[dict] | None = None,
                      feedback: str | None = None) -> dict:
        sess = self._session_factory()
        plan = sess.get(Plan, plan_id)
        if plan is None:
            return {"status": "not_found"}
        if tasks_json is not None:
            plan.tasks_json = tasks_json
        if feedback is not None:
            plan.feedback = feedback
        sess.commit()
        return {"updated": True}
