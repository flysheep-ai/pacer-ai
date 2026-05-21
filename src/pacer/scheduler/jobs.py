from __future__ import annotations
from sqlalchemy.orm import Session
from pacer.db.models import Student
from pacer.scheduler.client import post_system_event


def list_active_students(db: Session) -> list[int]:
    return [s.id for s in db.query(Student).all()]


def fire_for_each_student(event_type: str, db: Session):
    for sid in list_active_students(db):
        try:
            post_system_event(event_type, sid)
        except Exception:
            pass


def morning_job(db: Session): fire_for_each_student("morning_briefing", db)
def error_review_job(db: Session): fire_for_each_student("error_review", db)
def daily_report_job(db: Session): fire_for_each_student("daily_report", db)
def goodnight_job(db: Session): fire_for_each_student("goodnight", db)
def weekly_report_job(db: Session): fire_for_each_student("weekly_report", db)
