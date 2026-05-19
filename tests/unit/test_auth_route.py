import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = SessionLocal()
    sess.add(Student(id=1, name="Alice", grade=12, pin_hash=hash_pin("123456")))
    sess.commit(); sess.close()

    app = create_app(database_url=url)
    return TestClient(app)


def test_login_returns_session_token(client):
    resp = client.post("/auth/login", json={"student_id": 1, "pin": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body and len(body["token"]) > 20


def test_login_wrong_pin_rejected(client):
    resp = client.post("/auth/login", json={"student_id": 1, "pin": "999999"})
    assert resp.status_code == 401
