from __future__ import annotations
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import _utc_naive_now, get_db, hash_pin, issue_token, verify_pin
from pacer.config import get_settings
from pacer.db.models import Student

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("pacer.auth")


class LoginRequest(BaseModel):
    student_id: int
    pin: str


class LoginResponse(BaseModel):
    token: str
    student_id: int


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    s = db.get(Student, req.student_id)
    now = _utc_naive_now()

    if s is not None and s.login_locked_until and s.login_locked_until > now:
        raise HTTPException(status_code=429, detail="too many attempts; try later")

    if s is None:
        # Constant-ish work even for unknown ids to make user-enum harder.
        verify_pin(req.pin, "$2b$10$invalidsaltinvalidsaltinvalidsaltinvalidsaltinvalidsalt")
        raise HTTPException(status_code=401, detail="invalid credentials")

    ok, needs_upgrade = verify_pin(req.pin, s.pin_hash)
    if not ok:
        s.failed_login_count = (s.failed_login_count or 0) + 1
        if s.failed_login_count >= settings.login_max_attempts:
            s.login_locked_until = now + timedelta(seconds=settings.login_lockout_seconds)
            s.failed_login_count = 0
            log.warning("login lockout student=%s", s.id)
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")

    if needs_upgrade:
        s.pin_hash = hash_pin(req.pin)
        log.info("upgraded legacy pin hash student=%s", s.id)
    s.failed_login_count = 0
    s.login_locked_until = None
    db.commit()
    token = issue_token(s.id, db)
    return LoginResponse(token=token, student_id=s.id)
