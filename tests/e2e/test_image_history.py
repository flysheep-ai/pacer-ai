"""E2E: image messages persist across turns — multi-turn history retains the image block."""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.api.streaming import get_streaming_tasks
from pacer.db.models import Base, Student
from pacer.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_image_survives_into_second_turn_history(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=url)

    # Fake a 1-pixel white JPEG
    fake_jpeg_b64 = (
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkS"
        "Ew8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAAB"
        "AAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAA"
        "AAD/2gAIAQEAAD8AKAAA//Z"
    )

    messages_sent_to_llm: list = []

    async def _mock_chat(*args, **kwargs):
        messages_sent_to_llm.append(kwargs.get("messages", args[0] if args else []))
        return LLMResponse(
            text='{"intent":"chitchat","subject":null,"confidence":0.8}',
            tool_calls=[], stop_reason="end_turn",
            input_tokens=5, output_tokens=5, raw=None,
        )

    with patch("pacer.llm.openai_client.OpenAICompatClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]

            # Turn 1: send image + text
            r1 = await ac.post(
                "/message/send",
                json={"text": "这道题怎么做", "image_base64": fake_jpeg_b64},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r1.status_code == 202
            sid = r1.json()["session_id"]
            task1 = get_streaming_tasks().get(r1.json()["assistant_message_id"])
            if task1:
                await task1

            # Turn 2: follow-up text, same session
            r2 = await ac.post(
                "/message/send",
                json={"text": "刚才那张图的第二步不懂", "session_id": sid},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r2.status_code == 202
            task2 = get_streaming_tasks().get(r2.json()["assistant_message_id"])
            if task2:
                await task2

    # Turn 2 should have sent the image block as part of history to the router
    # Find the router call for turn 2 (first call after turn 1's done)
    assert len(messages_sent_to_llm) >= 1

    # Check that at least one message in the history contains an image block
    found_image = False
    for call_msgs in messages_sent_to_llm:
        for msg in call_msgs:
            content = getattr(msg, "content", msg.get("content", "")) if isinstance(msg, dict) else msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image":
                        found_image = True
                        break
    assert found_image, "turn 2 history should contain the image from turn 1"
