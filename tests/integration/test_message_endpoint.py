import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin
from pacer.llm.client import LLMResponse


@pytest.fixture
def client_and_token(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = SessionLocal()
    sess.add(Student(id=1, name="Alice", grade=12, pin_hash=hash_pin("123456")))
    sess.commit(); sess.close()
    app = create_app(database_url=url)
    client = TestClient(app)
    token = client.post("/auth/login", json={"student_id": 1, "pin": "123456"}).json()["token"]
    return client, token


def test_send_message_persists_and_returns_reply(client_and_token):
    client, token = client_and_token

    def _rsp(text="Hi Alice!", tc=None, sr="end_turn"):
        return LLMResponse(
            text=text, tool_calls=tc or [], stop_reason=sr,
            input_tokens=10, output_tokens=5, raw=None,
        )

    fake_resp = _rsp("Hi Alice!")
    with patch("pacer.api.routes.message.LLMClient.chat", new=AsyncMock(return_value=fake_resp)):
        resp = client.post(
            "/message/send", json={"text": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Hi Alice!"
    assert "session_id" in body
