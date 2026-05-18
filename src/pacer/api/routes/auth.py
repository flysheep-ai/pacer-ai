from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, hash_pin, issue_token
from pacer.db.models import Student

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    student_id: int
    pin: str


class LoginResponse(BaseModel):
    token: str
    student_id: int


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    s = db.get(Student, req.student_id)
    if s is None or s.pin_hash != hash_pin(req.pin):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_token(s.id)
    return LoginResponse(token=token, student_id=s.id)
