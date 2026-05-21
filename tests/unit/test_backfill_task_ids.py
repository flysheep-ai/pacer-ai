import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Plan, Student
from scripts.backfill_task_ids import backfill_task_ids


def _setup(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return url, engine


def test_backfill_fills_missing_ids_and_done_defaults(tmp_path):
    url, engine = _setup(tmp_path)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"subject": "math"}, {"subject": "english", "done": True}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 2
    with Session(engine) as s:
        p = s.get(Plan, 1)
        for t in p.tasks_json:
            assert isinstance(t.get("id"), str) and len(t["id"]) == 36
        assert p.tasks_json[0]["done"] is False
        assert p.tasks_json[1]["done"] is True


def test_backfill_is_idempotent(tmp_path):
    url, engine = _setup(tmp_path)
    existing_id = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"id": existing_id, "subject": "math", "done": False}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 0
    with Session(engine) as s:
        assert s.get(Plan, 1).tasks_json[0]["id"] == existing_id


def test_backfill_skips_non_dict_entries(tmp_path):
    url, engine = _setup(tmp_path)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=["bare string entry", {"subject": "math"}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 1
