import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin
from pacer.llm.client import LLMResponse


def _rsp(text):
    return LLMResponse(
        text=text, tool_calls=[], stop_reason="end_turn",
        input_tokens=10, output_tokens=5, raw=None,
    )


@pytest.fixture
def client_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    db = tmp_path / "e2e.db"
    url = f"sqlite:///{db}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = SessionLocal()
    s.add(Student(id=42, name="ZeroDay", grade=12, pin_hash=hash_pin("000000")))
    s.commit(); s.close()
    app = create_app(database_url=url)
    client = TestClient(app)
    tok = client.post("/auth/login", json={"student_id": 42, "pin": "000000"}).json()["token"]
    return client, tok


def test_two_turn_conversation_persists(client_token):
    """Two-turn conversation: each send returns 202 ack, session_id persists."""
    client, token = client_token
    replies = [
        _rsp('{"intent":"chitchat","subject":null,"confidence":0.8}'),  # router turn 1
        _rsp("你好，ZeroDay！"),  # homeroom turn 1
        _rsp('{"intent":"chitchat","subject":null,"confidence":0.6}'),  # router turn 2
        _rsp("你之前说过你想冲清华。"),  # homeroom turn 2
    ]
    with patch("pacer.llm.client.LLMClient.chat",
               new=AsyncMock(side_effect=replies)):
        r1 = client.post(
            "/message/send", json={"text": "你好"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 202
        body1 = r1.json()
        assert "session_id" in body1
        assert "assistant_message_id" in body1
        sid = body1["session_id"]

        r2 = client.post(
            "/message/send",
            json={"text": "我的目标是什么？", "session_id": sid},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 202
        assert r2.json()["session_id"] == sid
