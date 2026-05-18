"""Seed a dev student for local manual testing.

Usage: python scripts/seed_dev_student.py
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.config import get_settings
from pacer.db.models import Base, Student
from pacer.api.deps import hash_pin


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        existing = s.query(Student).filter_by(id=1).first()
        if existing is None:
            s.add(Student(id=1, name="开发学生", grade=12, pin_hash=hash_pin("123456")))
            s.commit()
            print("seeded student id=1, pin=123456")
        else:
            print("student id=1 already exists; nothing to do")


if __name__ == "__main__":
    main()
