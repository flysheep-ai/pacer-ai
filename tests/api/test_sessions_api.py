from __future__ import annotations

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.db.models import Base, Student, ChatSession, Message


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="test", grade=3, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=db_url)
    return TestClient(app)


def _auth_headers(client) -> dict[str, str]:
    r = client.post("/auth/login", json={"student_id": 1, "pin": "123456"})
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_sessions_empty(client):
    r = client.get("/sessions/", headers=_auth_headers(client))
    assert r.status_code == 200
    assert r.json() == []


def test_list_sessions_with_data(client):
    headers = _auth_headers(client)
    db = deps._SessionLocal()
    sess = ChatSession(id=1, student_id=1, status="active", last_active_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(sess)
    db.add(Message(id=1, session_id=1, role="user", content="Hello, how are you?"))
    db.commit()
    db.close()

    r = client.get("/sessions/", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["title"] == "Hello, how are you?"
    assert items[0]["message_count"] == 1


def test_get_session(client):
    headers = _auth_headers(client)
    db = deps._SessionLocal()
    sess = ChatSession(id=10, student_id=1, status="active", last_active_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(sess)
    db.add(Message(id=10, session_id=10, role="user", content="Test title message"))
    db.commit()
    db.close()

    r = client.get("/sessions/10", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == 10
    assert data["title"] == "Test title message"


def test_get_session_not_found(client):
    r = client.get("/sessions/9999", headers=_auth_headers(client))
    assert r.status_code == 404


def test_list_messages(client):
    headers = _auth_headers(client)
    db = deps._SessionLocal()
    sess = ChatSession(id=20, student_id=1, status="active")
    db.add(sess)
    db.add(Message(id=20, session_id=20, role="user", content="Hi"))
    db.add(Message(id=21, session_id=20, role="assistant", content="Hello there"))
    db.commit()
    db.close()

    r = client.get("/sessions/20/messages", headers=headers)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_list_messages_not_found(client):
    r = client.get("/sessions/9999/messages", headers=_auth_headers(client))
    assert r.status_code == 404


def test_rename_session(client):
    headers = _auth_headers(client)
    db = deps._SessionLocal()
    sess = ChatSession(id=30, student_id=1, status="active")
    db.add(sess)
    db.commit()
    db.close()

    r = client.patch("/sessions/30", json={"title": "New title"}, headers=headers)
    assert r.status_code == 204


def test_rename_session_not_found(client):
    r = client.patch("/sessions/9999", json={"title": "New title"}, headers=_auth_headers(client))
    assert r.status_code == 404


def test_delete_session(client):
    headers = _auth_headers(client)
    db = deps._SessionLocal()
    sess = ChatSession(id=40, student_id=1, status="active")
    db.add(sess)
    db.commit()
    db.close()

    r = client.delete("/sessions/40", headers=headers)
    assert r.status_code == 204

    # Verify it's archived
    db = deps._SessionLocal()
    s = db.get(ChatSession, 40)
    assert s is not None
    assert s.status == "archived"
    db.close()


def test_delete_session_not_found(client):
    r = client.delete("/sessions/9999", headers=_auth_headers(client))
    assert r.status_code == 404


def test_unauthorized(client):
    r = client.get("/sessions/")
    assert r.status_code == 401
