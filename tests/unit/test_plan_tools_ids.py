import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.tools.plan_tools import CreatePlanTool


@pytest.fixture
def student_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.commit()
    return engine


@pytest.mark.asyncio
async def test_create_plan_assigns_uuid_and_done_false(student_session):
    engine = student_session
    tool = CreatePlanTool(session_factory=lambda: Session(engine), student_id=1)
    out = await tool.execute(type="daily", tasks=[
        {"subject": "math", "duration_min": 30},
        {"subject": "english", "duration_min": 20, "done": True},
    ])
    assert "plan_id" in out
    tasks = out["tasks"]
    assert len(tasks) == 2
    for t in tasks:
        assert isinstance(t.get("id"), str) and len(t["id"]) == 36
    assert tasks[0]["done"] is False
    # Explicit done=True from caller is preserved
    assert tasks[1]["done"] is True


@pytest.mark.asyncio
async def test_create_plan_preserves_caller_supplied_id(student_session):
    engine = student_session
    tool = CreatePlanTool(session_factory=lambda: Session(engine), student_id=1)
    out = await tool.execute(type="daily", tasks=[
        {"id": "fixed-id-1234", "subject": "math"},
    ])
    assert out["tasks"][0]["id"] == "fixed-id-1234"
