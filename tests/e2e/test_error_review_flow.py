"""E2E: starting an error review drives the subject teacher through
mark_error_reviewed → mastery update.

We script the LLM with three responses:
  1. router: subject_qa / math
  2. subject teacher: tool_use mark_error_reviewed(correct=True)
  3. subject teacher: final text reply

The agent loop is non-streaming throughout (because the streaming runner
uses chat() per iteration and only chunk-emits the final text), so a flat
list of LLMResponse objects is enough.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.api.streaming import get_streaming_tasks
from pacer.db.models import Base, ErrorRecord, Question, Student
from pacer.llm.client import LLMResponse


def _resp(text: str = "", tool_calls=None, stop: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        text=text, tool_calls=tool_calls or [], stop_reason=stop,
        input_tokens=5, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_start_review_runs_full_loop_and_updates_mastery(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("PACER_INTERNAL_TOKEN", "test-token")
    url = f"sqlite:///{tmp_path}/t.db"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Question(id=11, subject="math", stem="求 f(x)=x^2 的导数", answer="2x"))
        s.add(ErrorRecord(
            id=21, student_id=1, question_id=11,
            user_answer="x", correct_answer="2x", error_type="concept",
            source="text", mastery_level=0.5, review_count=0,
        ))
        s.commit()
    app = create_app(database_url=url)

    call_index = 0

    async def _mock_chat(*args, **kwargs):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            return _resp(text='{"intent":"subject_qa","subject":"math","confidence":0.95}')
        if call_index == 2:
            return _resp(
                tool_calls=[{
                    "id": "tc1",
                    "name": "mark_error_reviewed",
                    "input": {"error_record_id": 21, "correct": True},
                }],
                stop="tool_use",
            )
        return _resp(text="不错，看来你掌握了。我们今天就到这里。")

    with patch("pacer.llm.client.LLMClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]
            r = await ac.post(
                "/errors/21/start-review",
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 202
            msg_id = r.json()["assistant_message_id"]
            task = get_streaming_tasks().get(msg_id)
            if task is not None:
                await task

    with Session(engine) as s:
        e = s.get(ErrorRecord, 21)
        assert e.review_count == 1
        assert e.mastery_level == pytest.approx(0.65, abs=0.001)
        assert e.last_reviewed_at is not None
