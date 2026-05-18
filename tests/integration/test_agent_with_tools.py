import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student, MemoryEntry
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool, SearchMemoryTool
from pacer.agent.loop import AgentLoop
from pacer.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_agent_remembers_via_tool():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="X", grade=12, pin_hash="h")
    sess.add(s); sess.commit()

    reg = ToolRegistry()
    reg.register(RememberTool(lambda: sess, s.id))
    reg.register(SearchMemoryTool(lambda: sess, s.id))

    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        LLMResponse(
            text="", tool_calls=[{
                "id": "t1", "name": "remember",
                "input": {"type": "goal", "key": "target", "content": "清华"},
            }],
            stop_reason="tool_use", input_tokens=10, output_tokens=5, raw=None,
        ),
        LLMResponse(
            text="Saved!", tool_calls=[], stop_reason="end_turn",
            input_tokens=8, output_tokens=4, raw=None,
        ),
    ])

    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys")
    result = await loop.run("Remember I want Tsinghua", history=[])
    assert result.final_text == "Saved!"

    entries = sess.query(MemoryEntry).filter_by(student_id=s.id).all()
    assert len(entries) == 1
    assert entries[0].content == "清华"
