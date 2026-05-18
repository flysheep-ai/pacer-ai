import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.tools.memory_tools import SearchMemoryTool, RememberTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool


@pytest.fixture
def db_and_student():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="小明", grade=12, pin_hash="h", profile_json={"target_score": 600})
    sess.add(s); sess.commit()
    yield sess, s.id
    sess.close()


@pytest.mark.asyncio
async def test_remember_and_search_round_trip(db_and_student):
    sess, sid = db_and_student
    remember = RememberTool(session_factory=lambda: sess, student_id=sid)
    search = SearchMemoryTool(session_factory=lambda: sess, student_id=sid)
    await remember.execute(type="goal", key="target", content="清华计算机", importance=0.9)
    res = await search.execute(query="清华")
    assert len(res["entries"]) == 1
    assert res["entries"][0]["content"] == "清华计算机"


@pytest.mark.asyncio
async def test_get_and_update_profile(db_and_student):
    sess, sid = db_and_student
    getter = GetStudentProfileTool(session_factory=lambda: sess, student_id=sid)
    updater = UpdateStudentProfileTool(session_factory=lambda: sess, student_id=sid)
    profile = await getter.execute()
    assert profile["name"] == "小明"
    assert profile["profile_json"]["target_score"] == 600
    await updater.execute(updates={"target_school": "清华大学", "profile_json.bedtime": "22:30"})
    refreshed = await getter.execute()
    assert refreshed["target_school"] == "清华大学"
    assert refreshed["profile_json"]["bedtime"] == "22:30"
    assert refreshed["profile_json"]["target_score"] == 600
