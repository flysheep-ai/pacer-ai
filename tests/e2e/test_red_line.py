"""E2E: red-line keywords short-circuit the LLM and return crisis resources."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.db.models import Base, MoodLog, Student
from pacer.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_self_harm_text_short_circuits_and_logs_mood(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=url)

    llm_called = False

    async def _mock_chat(*args, **kwargs):
        nonlocal llm_called
        llm_called = True
        return LLMResponse(
            text="should not be reached", tool_calls=[], stop_reason="end_turn",
            input_tokens=0, output_tokens=0, raw=None,
        )

    with patch("pacer.llm.client.LLMClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]
            r = await ac.post(
                "/message/send",
                json={"text": "我想自杀"},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 202
            ack = r.json()
            assert "assistant_message_id" in ack

    # LLM must NOT have been called
    assert not llm_called

    # Stored assistant message must contain the escalation response
    with Session(engine) as s:
        msg_id = ack["assistant_message_id"]
        from pacer.db.models import Message
        msg = s.get(Message, msg_id)
        assert msg is not None
        assert "400-161-9995" in msg.content
        assert msg.agent == "mood_companion"

        # MoodLog must exist with red_flag=True
        log = s.query(MoodLog).filter_by(student_id=1).order_by(MoodLog.id.desc()).first()
        assert log is not None
        assert log.red_flag is True
