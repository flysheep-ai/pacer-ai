from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db
from pacer.config import get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


class SystemEventReq(BaseModel):
    type: str
    student_id: int
    payload: dict | None = None


def _verify_internal_token(
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
    request: Request = None,
):
    settings = get_settings()
    if not x_internal_token or x_internal_token != settings.internal_token:
        raise HTTPException(status_code=403, detail="forbidden")
    if request is not None:
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="not local")


@router.post("/system-event", dependencies=[Depends(_verify_internal_token)])
async def handle_system_event(
    req: SystemEventReq, request: Request, db: Session = Depends(get_db),
):
    from pacer.companion.briefing import generate_morning_plan
    from pacer.companion.error_review import run_error_review
    from pacer.companion.daily_report import generate_daily_report
    from pacer.companion.backlog import enqueue_or_publish

    student_id = req.student_id
    if req.type == "morning_briefing":
        text = await generate_morning_plan(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "morning_briefing", text)
    elif req.type == "error_review":
        text = await run_error_review(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "error_review", text)
    elif req.type == "daily_report":
        text = await generate_daily_report(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "daily_report", text)
    elif req.type == "goodnight":
        await enqueue_or_publish(request.app.state, student_id, "goodnight", "晚安，好好休息～")
    elif req.type == "weekly_report":
        from pacer.companion.weekly_report import generate_weekly_report
        text = await generate_weekly_report(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "weekly_report", text)
    else:
        raise HTTPException(status_code=400, detail=f"unknown event type {req.type!r}")
    return {"status": "ok"}
