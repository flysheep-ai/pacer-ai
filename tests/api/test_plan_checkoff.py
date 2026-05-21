from __future__ import annotations
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.db.models import Base, Plan, Student


def _auth(client: TestClient, sid: int = 1, pin: str = "123456") -> dict[str, str]:
    r = client.post("/auth/login", json={"student_id": sid, "pin": pin})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client_with_plan(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    task_a = str(uuid.uuid4())
    task_b = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Plan(
            id=10, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[
                {"id": task_a, "subject": "math", "done": False},
                {"id": task_b, "subject": "english", "done": False},
            ],
            generated_by="homeroom",
        ))
        s.commit()
    return TestClient(create_app(database_url=url)), task_a, task_b


def test_patch_task_marks_done(client_with_plan):
    client, task_a, task_b = client_with_plan
    h = _auth(client)
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": True}, headers=h)
    assert r.status_code == 204
    plan = client.get("/plans/10", headers=h).json()
    targets = {t["id"]: t["done"] for t in plan["tasks"]}
    assert targets[task_a] is True
    assert targets[task_b] is False


def test_patch_task_can_toggle_back_to_false(client_with_plan):
    client, task_a, _ = client_with_plan
    h = _auth(client)
    client.patch(f"/plans/10/tasks/{task_a}", json={"done": True}, headers=h)
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": False}, headers=h)
    assert r.status_code == 204
    plan = client.get("/plans/10", headers=h).json()
    assert next(t for t in plan["tasks"] if t["id"] == task_a)["done"] is False


def test_patch_task_404_when_plan_owned_by_other_student(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    other_task = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Student(id=2, name="B", grade=12, pin_hash=deps.hash_pin("000000")))
        s.add(Plan(
            id=20, student_id=2, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"id": other_task, "subject": "math", "done": False}],
            generated_by="homeroom",
        ))
        s.commit()
    client = TestClient(create_app(database_url=url))
    r = client.patch(f"/plans/20/tasks/{other_task}", json={"done": True}, headers=_auth(client))
    assert r.status_code == 404


def test_patch_task_404_unknown_task_id(client_with_plan):
    client, _, _ = client_with_plan
    r = client.patch(
        f"/plans/10/tasks/{uuid.uuid4()}",
        json={"done": True}, headers=_auth(client),
    )
    assert r.status_code == 404


def test_patch_task_requires_auth(client_with_plan):
    client, task_a, _ = client_with_plan
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": True})
    assert r.status_code == 401
