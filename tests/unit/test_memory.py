import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.memory.persistent import PersistentMemory


@pytest.fixture
def session_with_student():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    student = Student(name="小明", grade=12, pin_hash="h")
    s.add(student)
    s.commit()
    yield s, student.id
    s.close()


def test_add_and_retrieve_memory(session_with_student):
    s, student_id = session_with_student
    mem = PersistentMemory(s, student_id)
    entry = mem.add(type="weakness", key="导数:切线方程", content="多次错")
    assert entry.id is not None
    fetched = mem.find_relevant("切线", max_results=5)
    assert len(fetched) == 1
    assert fetched[0].key == "导数:切线方程"


def test_find_relevant_ranks_by_keyword_overlap(session_with_student):
    s, student_id = session_with_student
    mem = PersistentMemory(s, student_id)
    mem.add(type="goal", key="目标院校", content="清华大学计算机系")
    mem.add(type="habit", key="作息", content="晚 22:30 入睡早 06:30 起")
    mem.add(type="weakness", key="导数:切线方程", content="切线方程斜率多次出错")
    results = mem.find_relevant("切线方程", max_results=2)
    assert results[0].content.startswith("切线方程")


def test_isolated_per_student(session_with_student):
    s, student_id = session_with_student
    other = Student(name="小红", grade=12, pin_hash="h")
    s.add(other); s.commit()
    mem_a = PersistentMemory(s, student_id)
    mem_b = PersistentMemory(s, other.id)
    mem_a.add(type="goal", key="g", content="A's goal")
    mem_b.add(type="goal", key="g", content="B's goal")
    a_results = mem_a.find_relevant("goal", max_results=10)
    b_results = mem_b.find_relevant("goal", max_results=10)
    assert len(a_results) == 1 and a_results[0].content == "A's goal"
    assert len(b_results) == 1 and b_results[0].content == "B's goal"
