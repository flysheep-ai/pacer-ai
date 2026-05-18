from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
def get_profile(
    student_id: int = Depends(current_student_id),
    db: Session = Depends(get_db),
):
    tool = GetStudentProfileTool(session_factory=lambda: db, student_id=student_id)
    return asyncio.run(tool.execute())


@router.patch("/")
def patch_profile(
    updates: dict,
    student_id: int = Depends(current_student_id),
    db: Session = Depends(get_db),
):
    tool = UpdateStudentProfileTool(session_factory=lambda: db, student_id=student_id)
    return asyncio.run(tool.execute(updates=updates))
