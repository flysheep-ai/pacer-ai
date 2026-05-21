from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.api.streaming import get_streaming_tasks
from pacer.db.models import Base, KnowledgePoint, Message, Student
from pacer.llm.client import LLMResponse


def _llm(text="ok"):
    return LLMResponse(
        text=text, tool_calls=[], stop_reason="end_turn",
        input_tokens=5, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_start_mastery_review_creates_session(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(KnowledgePoint(id=42, subject="math", chapter="函数",
               point_name="导数的几何意义", difficulty=3, prereq_ids=[]))
        s.commit()
    app = create_app(database_url=url)

    async def _mock_chat(*args, **kwargs):
        return _llm('{"intent":"subject_qa","subject":"math","confidence":0.9}')

    with patch("pacer.llm.client.LLMClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]
            r = await ac.post(
                "/mastery/start-review",
                json={"knowledge_point_id": 42},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 202
            body = r.json()
            session_id = body["session_id"]
            msg_id = body["assistant_message_id"]
            task = get_streaming_tasks().get(msg_id)
            if task is not None:
                await task

    with Session(engine) as s:
        msgs = (s.query(Message).filter_by(session_id=session_id)
                 .order_by(Message.id).all())
        assert len(msgs) >= 2
        seed = msgs[0]
        assert seed.role == "user"
        assert "[复习知识点 #42]" in seed.content
        assert "导数的几何意义" in seed.content
        assert msgs[1].role == "assistant"


@pytest.mark.asyncio
async def test_start_mastery_review_404_unknown_kp(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        tok = (await ac.post(
            "/auth/login", json={"student_id": 1, "pin": "123456"},
        )).json()["token"]
        r = await ac.post(
            "/mastery/start-review",
            json={"knowledge_point_id": 99999},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_start_mastery_review_requires_auth(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        r = await ac.post("/mastery/start-review", json={"knowledge_point_id": 1})
        assert r.status_code == 401
