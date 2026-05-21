from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pacer.api.streaming import get_streaming_tasks
_streaming_tasks = get_streaming_tasks()
from pacer.api.server import create_app
from pacer.api.deps import hash_pin
from pacer.db.models import Base, Message, Student
from pacer.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_streaming_send_returns_ack_and_finalizes_message(tmp_path, monkeypatch):
    """POST /message/send returns 202 ack; background task finalizes message with status='done'."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    db_path = tmp_path / "test_stream.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    # Create a test student
    with Session(engine) as sess:
        sess.add(Student(id=1, name="Alice", grade=12, pin_hash=hash_pin("123456")))
        sess.commit()

    app = create_app(database_url=url)

    # Track how many times chat() is called so we can decide what to return
    _call_count = 0

    async def _mock_chat(*args, **kwargs):
        nonlocal _call_count
        _call_count += 1
        if _call_count == 1:
            # Router call — return a routing decision
            return LLMResponse(
                text='{"intent":"chitchat","subject":null,"confidence":0.8}',
                tool_calls=[],
                stop_reason="end_turn",
                input_tokens=10,
                output_tokens=5,
                raw=None,
            )
        elif _call_count <= 3:
            # Agent loop early iterations — call a tool that exists on homeroom.
            return LLMResponse(
                text="",
                tool_calls=[
                    {
                        "id": f"call_{_call_count}",
                        "name": "get_today_plan",
                        "input": {},
                    },
                ],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
                raw=None,
            )
        # Final turn: text-only response gets chunk-emitted by the agent loop.
        return LLMResponse(
            text="这是一道导数题，先看条件…",
            tool_calls=[],
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=5,
            raw=None,
        )

    with patch(
        "pacer.llm.client.LLMClient.chat",
        new=AsyncMock(side_effect=_mock_chat),
    ):
        if True:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test",
            ) as ac:
                # Login
                r = await ac.post(
                    "/auth/login", json={"student_id": 1, "pin": "123456"},
                )
                token = r.json()["token"]

                # Send a message
                resp = await ac.post(
                    "/message/send",
                    json={"text": "讲一道导数题"},
                    headers={"Authorization": f"Bearer {token}"},
                )

                assert resp.status_code == 202
                ack = resp.json()
                assert "session_id" in ack
                assert "assistant_message_id" in ack
                assert isinstance(ack["session_id"], int)
                assert isinstance(ack["assistant_message_id"], int)

                # The background task runs on the same event loop via ASGITransport.
                # Await it directly to ensure it completes.
                msg_id = ack["assistant_message_id"]
                task = _streaming_tasks.get(msg_id)
                if task is not None:
                    await task

    # Verify the message was finalized in the DB
    with Session(engine) as sess:
        msg = sess.get(Message, msg_id)
        assert msg is not None
        assert msg.status == "done"
        assert "导数题" in msg.content
